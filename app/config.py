import os

DEBUG = 10
INFO = 20
WARN = 30
ERROR = 40
DISABLED = 50

dir_path = os.path.dirname(os.path.realpath(__file__))

LOGDIR = dir_path + "/logs"
RESULTSPATH = dir_path + "/results.csv"
TMPMODELDIR = dir_path + "/tmp"
MODELDIR = dir_path + "/zoo"
