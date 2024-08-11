import os
import configparser
import shutil
from PIL import Image, ExifTags
import pillow_heif
from PIL.ExifTags import TAGS, GPSTAGS
from geopy.geocoders import Nominatim
from GPSPhoto import gpsphoto

pillow_heif.register_heif_opener() # opener for .heic files

def extract_exif(file_path):
    image = Image.open(file_path)
    exif_data = image.getexif()

    # Convert EXIF data to a more readable dictionary format
    return {"exif_tags":{ExifTags.TAGS.get(tag): value for tag, value in exif_data.items()} if exif_data else None, "exif_data":exif_data}

def extract_gps_info(exif_data):
    # Find the tag number for GPSInfo
    gps_info_tag = next(tag for tag, name in ExifTags.TAGS.items() if name == 'GPSInfo')
    print(gps_info_tag)

    # Extract GPSInfo using the tag number directly
    gps_info = exif_data.get(gps_info_tag)
    print(exif_data.get(gps_info))
    if not gps_info:
        print("No GPS data found.")
        return None

    gps_data = exif_data.get_ifd(gps_info)
    
    return gps_data

# Load config
config = configparser.ConfigParser()
config.read('config.ini')

source_folder = config['Folders']['source_folder']
destination_folder = config['Folders']['destination_folder']
duplicate_folder = config["Folders"]["duplicate_folder"]

example_file = config["Files"]["example_file"]

print("File location: " + example_file)
image_data = extract_exif(example_file)
print("File tags: " + str(image_data["exif_tags"]))
image_gps = extract_gps_info(image_data["exif_data"])
print("File GPS data: " + image_gps)

