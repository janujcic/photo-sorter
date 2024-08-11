import os
import configparser
import shutil


# Load config
config = configparser.ConfigParser()
config.read('config.ini')

source_folder = config['Folders']['source_folder']
destination_folder = config['Folders']['destination_folder']
example_file = config["Folders"]["example_file"]

print(example_file)
