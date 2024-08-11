import os
import configparser
import shutil
from PIL import Image, ExifTags
import pillow_heif
from PIL.ExifTags import TAGS, GPSTAGS
from geopy.geocoders import Nominatim
from GPSPhoto import gpsphoto
import imagehash
from collections import defaultdict
import re

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
    print(gps_info)
    if not gps_info:
        print("No GPS data found.")
        return None

    gps_data = exif_data.get_ifd(gps_info)
    
    return gps_data

def get_image_hash(image_path):
    try:
        with Image.open(image_path) as img:
            return imagehash.average_hash(img)
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return None

def check_if_duplicate_image(source_folder, image_name, hash_map):
    # Path of the current image
    image_path = os.path.join(source_folder, image_name)

    if image_name.lower().endswith(('.mp3', '.mp4', '.mov')):
        if is_duplicate_name(image_name):
            return {"duplicate": True, "image_name": image_name, "image_hash": "video_"+image_name}
        else:
            return {"duplicate": False, "image_name": image_name, "image_hash": "video_"+image_name}
        
    # Get image hash
    image_hash = get_image_hash(image_path)
    
    if image_hash is not None:
        # Check if the name pattern indicates a duplicate
        if is_duplicate_name(image_name):
            return {"duplicate": True, "image_name": image_name, "image_hash": str(image_hash)}

        # Check if the hash already exists in the hash_map
        hash_key = str(image_hash)
        if hash_key in hash_map:
            for original_name in hash_map[hash_key]:
                return {"duplicate": True, "image_name": image_name, "image_hash": str(image_hash)}
        else:
            return {"duplicate": False, "image_name": image_name, "image_hash": str(image_hash)}
    else:
        return None

def is_duplicate_name(file_name):
    """
    Check if the current image name indicates a duplicate based on the naming pattern:
    - {some_photo_name} - Copy
    - {some_photo_name} - ({number}) where {number} can be any integer
    """
    # Check for the " - Copy" pattern
    if re.search(r" - Copy\.", file_name):
        return True

    # Check for the " ({number})" pattern
    if re.search(r" \(\d+\)\.", file_name):
        return True

def verify_duplicates(duplicates_list, hash_map):
    hash_not_found = []
    for key, value in duplicates_list.items():
        key_to_compare = value
        if ("video_" in value):
            file_type = value.split(".")[1]
            video_hash = value.split(" ")[0]
            key_to_compare = video_hash + "." + file_type
        if key_to_compare in hash_map:
            continue
        else:
            hash_not_found.append(key)

    for k in hash_not_found:
        del duplicates_list[k]
        

    return duplicates_list, hash_not_found


def move_duplicates(source_folder, file_names, duplicates_folder):
    for file_name in file_names:
        file_path = os.path.join(source_folder, file_name)
        try:
            shutil.move(file_path, duplicates_folder)
            print(f"Moved duplicate: {file_path}")
        except Exception as e:
            print(f"Error moving {file_path}: {e}")


if __name__ == "__main__":
    # Load config
    config = configparser.ConfigParser()
    config.read('config.ini')

    # get all the folder configurations
    source_folder = config['Folders']['source_folder']
    sorted_photos_folder = config['Folders']['sorted_photos_folder']
    duplicate_photos_folder = config["Folders"]["duplicate_photos_folder"]
    broken_photos_folder = config["Folders"]["broken_photos_folder"]
    manual_check_duplicates = config["Folders"]["config["Folders"]["broken_photos_folder"]"]

    # example file path for testing
    example_file_path_path = config["Files"]["example_file_path"]

    # Dictionary to map image hashes to their file names
    hash_map = defaultdict(list)
    duplicate_images = {}
    broken_images = [] # images that either couldn't be processed or cannot be identified as duplicates

    # get all the image names from the source_folder
    image_names = [f for f in os.listdir(source_folder) if os.path.isfile(os.path.join(source_folder, f))]
    print("Number of images: " + str(len(image_names)))

    for i in range(len(image_names)):
        duplicate_evaluation = check_if_duplicate_image(source_folder, image_names[i], hash_map)
        if duplicate_evaluation is None:
            broken_images.append(image_names[i])
            continue;
        if (duplicate_evaluation["duplicate"]):
            duplicate_images[duplicate_evaluation["image_name"]] = duplicate_evaluation["image_hash"]
        elif duplicate_evaluation:
            hash_map[duplicate_evaluation["image_hash"]] = image_names[i]

    #print("Hash map: " + str(hash_map))
    #print("Duplicates paths: " + str(duplicate_images))

    # double check if the hash for the duplicates exist, otherwise add them to the manual check duplicates
    updated_duplicate_images, manual_check_duplicates = verify_duplicates(duplicate_images, hash_map)
    print("Duplicates paths: " + str(updated_duplicate_images))
    print("Files to manually check for duplicates: " + str(manual_check_duplicates))

    move_duplicates(source_folder, manual_check_duplicates, manual_check_duplicates)
    move_duplicates(source_folder, broken_images, broken_photos_folder)
    move_duplicates(source_folder, updated_duplicate_images, duplicate_photos_folder)


"""
print("File location: " + example_file_path)
image_data = extract_exif(example_file_path)
print("File tags: " + str(image_data["exif_tags"]))
image_gps = extract_gps_info(image_data["exif_data"])
print("File GPS data: " + str(image_gps))
"""
