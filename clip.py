import numpy as np
import soundfile as sf
from PyQt5 import QtCore
import configparser
from zipfile import ZipFile
from io import BytesIO, StringIO, TextIOWrapper
import unicodedata


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


def basename(s):
    str = strip_accents(s)
    return str.split('/')[-1]


class Communicate(QtCore.QObject):

    updateUI = QtCore.pyqtSignal()


class Clip():

    STOP = 0
    STARTING = 1
    START = 2
    STOPPING = 3

    TRANSITION = {STOP: STARTING,
                  STARTING: STOP,
                  START: STOPPING,
                  STOPPING: START}
    STATE_DESCRIPTION = {0: "STOP",
                         1: "STARTING",
                         2: "START",
                         3: "STOPPING"}

    def __init__(self, audio_file, name=None,
                 volume=1, frame_offset=0, beat_offset=0.0, beat_diviser=1):

        if name is None:
            self.name = audio_file
        else:
            self.name = name
        self.volume = volume
        self.frame_offset = frame_offset
        self.beat_offset = beat_offset
        self.beat_diviser = beat_diviser
        self.state = Clip.STOP
        self.audio_file = audio_file
        self.last_offset = 0


class Song():

    def __init__(self, width, height):
        self.clips_matrix = [[None for y in range(height)]
                             for x in range(width)]
        self.clips = []
        self.data, self.samplerate = {}, {}
        self.volume = 1.0
        self.bpm = 120
        self.beat_per_bar = 4
        self.width = width
        self.height = height
        self.file_name = None

    def addClip(self, clip, x, y):
        if self.clips_matrix[x][y]:
            self.clips.remove(self.clips_matrix[x][y])
        self.clips_matrix[x][y] = clip
        self.clips.append(clip)
        clip.x = x
        clip.y = y

    def removeClip(self, clip):
        self.clips_matrix[clip.x][clip.y] = None
        self.clips.remove(clip)

    def toogle(self, x, y):
        clip = self.clips_matrix[x][y]
        if clip:
            clip.state = Clip.TRANSITION[clip.state]

    def channels(self, clip):
        return self.data[clip.audio_file].shape[1]

    def length(self, clip):
        return self.data[clip.audio_file].shape[0]

    def get_data(self, clip, channel, offset, length):
        channel %= self.channels(clip)
        if offset > (self.length(clip) - 1) or offset < 0 or length < 0:
            raise Exception("Invalid length or offset: {0} {1} {2}".
                            format(length, offset, self.length(clip)))
        if (length + offset) > self.length(clip):
            raise Exception("Index out of range : {0} + {1} > {2}".
                            format(length, offset, self.length(clip)))

        return (self.data[clip.audio_file][offset:offset+length, channel]
                * clip.volume)

    def save(self):
        if self.file_name:
            self.saveTo(self.file_name)
        else:
            raise Exception("No file specified")

    def saveTo(self, file):
        with ZipFile(file, 'w') as zip:
            song_file = configparser.ConfigParser()
            song_file['DEFAULT'] = {'volume': self.volume,
                                    'bpm': self.bpm,
                                    'beat_per_bar': self.beat_per_bar,
                                    'width': self.width,
                                    'height': self.height}
            for clip in self.clips:
                print(" clip at %s %s" % (clip.x, clip.y))
                clip_file = {'name': clip.name,
                             'volume': clip.volume,
                             'frame_offset': clip.frame_offset,
                             'beat_offset': clip.beat_offset,
                             'beat_diviser': clip.beat_diviser,
                             'audio_file': basename(
                                 clip.audio_file)}
                song_file["%s/%s" % (clip.x, clip.y)] = clip_file

            buffer = StringIO()
            song_file.write(buffer)
            zip.writestr('metadata.ini', buffer.getvalue())

            for member in self.data:
                buffer = BytesIO()
                sf.write(self.data[member], buffer,
                         self.samplerate[member],
                         subtype=sf.default_subtype('WAV'),
                         format='WAV')
                zip.writestr(member, buffer.getvalue())

        self.file_name = file


def load_song_from_file(file):
    with ZipFile(file) as zip:
        with zip.open('metadata.ini') as metadata_res:
            metadata = TextIOWrapper(metadata_res)
            parser = configparser.ConfigParser()
            parser.read_file(metadata)
            res = Song(parser['DEFAULT'].getint('width'),
                       parser['DEFAULT'].getint('height'))
            res.file_name = file
            res.volume = parser['DEFAULT'].getfloat('volume')
            res.bpm = parser['DEFAULT'].getfloat('bpm')
            res.beat_per_bar = parser['DEFAULT'].getint('beat_per_bar')

            # Loading wavs
            for member in zip.namelist():
                if member == 'metadata.ini':
                    continue
                buffer = BytesIO()
                wav_res = zip.open(member)
                buffer.write(wav_res.read())
                buffer.seek(0)
                data, samplerate = sf.read(buffer, dtype=np.float32)
                res.data[member] = data
                res.samplerate[member] = samplerate

            # loading clips
            for section in parser:
                if section == 'DEFAULT':
                    continue
                x, y = section.split('/')
                x, y = int(x), int(y)
                clip = Clip(parser[section]['audio_file'],
                            parser[section]['name'],
                            parser[section].getfloat('volume', 1.0),
                            parser[section].getint('frame_offset', 0),
                            parser[section].getfloat('beat_offset', 0.0),
                            parser[section].getint('beat_diviser'))
                res.addClip(clip, x, y)

    return res
