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
import reverse_geocode
import ffmpeg

def extract_exif(file_path):
    file_extension = os.path.splitext(file_path)[1].lower()

    if file_extension == '.heic' or file_extension == '.HEIC':
        # Use pillow-heif for HEIC format
        heif_image = pillow_heif.open_heif(file_path)
        exif_data = heif_image.getexif()
    else:
        # Use Pillow for other formats
        image = Image.open(file_path)
        exif_data = image._getexif()

    # Convert EXIF data to a more readable dictionary format
    return {ExifTags.TAGS.get(tag): value for tag, value in exif_data.items()} if exif_data else None

def convert_to_degrees(value):
    # Convert the tuple to degrees
    d, m, s = value
    return d + (m / 60.0) + (s / 3600.0)

def extract_lat_lon(gps_data):
    # Extract latitude and longitude
    lat = eval(gps_data['GPSLatitude'])
    lon = eval(gps_data['GPSLongitude'])
    
    # Convert to decimal degrees
    lat_decimal = convert_to_degrees(lat)
    lon_decimal = convert_to_degrees(lon)
    
    # Apply the hemisphere correction
    if gps_data['GPSLatitudeRef'] == 'S':
        lat_decimal = -lat_decimal
    if gps_data['GPSLongitudeRef'] == 'W':
        lon_decimal = -lon_decimal
    
    return lat_decimal, lon_decimal

def extract_image_gps_info(image_path):
    image = Image.open(image_path)
    image.verify()
    exif = image.getexif().get_ifd(0x8825)

    geo_tagging_info = {}
    if not exif:
        raise ValueError("No EXIF metadata found")
    else:
        gps_keys = ['GPSVersionID', 'GPSLatitudeRef', 'GPSLatitude', 'GPSLongitudeRef', 'GPSLongitude',
                    'GPSAltitudeRef', 'GPSAltitude', 'GPSTimeStamp', 'GPSSatellites', 'GPSStatus', 'GPSMeasureMode',
                    'GPSDOP', 'GPSSpeedRef', 'GPSSpeed', 'GPSTrackRef', 'GPSTrack', 'GPSImgDirectionRef',
                    'GPSImgDirection', 'GPSMapDatum', 'GPSDestLatitudeRef', 'GPSDestLatitude', 'GPSDestLongitudeRef',
                    'GPSDestLongitude', 'GPSDestBearingRef', 'GPSDestBearing', 'GPSDestDistanceRef', 'GPSDestDistance',
                    'GPSProcessingMethod', 'GPSAreaInformation', 'GPSDateStamp', 'GPSDifferential']

        for k, v in exif.items():
            try:
                geo_tagging_info[gps_keys[k]] = str(v)
            except IndexError:
                pass
        return extract_lat_lon(geo_tagging_info)

def get_data_from_geocode(geo_coords):
    return reverse_geocode.get(geo_coords)

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


def move_files(source_folder, file_names, target_folder):
    for file_name in file_names:
        file_path = os.path.join(source_folder, file_name)
        destination_path = os.path.join(target_folder, file_name)

        if os.path.exists(destination_path):
            print(f"File {file_name} already exists in {target_folder}. Skipping...")
            continue

        try:
            shutil.move(file_path, target_folder)
            print(f"Moved file: {file_path}")
        except Exception as e:
            print(f"Error moving {file_path}: {e}")

def copy_files(source_folder, file_names, target_folder):
    for file_name in file_names:
        file_path = os.path.join(source_folder, file_name)
        destination_path = os.path.join(target_folder, file_name)

        if os.path.exists(destination_path):
            print(f"File {file_name} already exists in {destination_path}. Skipping...")
            continue

        try:
            shutil.copy(file_path, destination_path)
            print(f"Copied file: {file_path}")
        except Exception as e:
            print(f"Error moving {file_path}: {e}")

def sort_duplicates(source_folder, manual_check_duplicates_folder, broken_photos_folder, duplicate_photos_folder):
    # Dictionary to map image hashes to their file names
    hash_map = defaultdict(list)
    duplicate_images = {}
    broken_images = [] # images that either couldn't be processed or cannot be identified as duplicates

    # get all the image names from the source_folder
    image_names = [f for f in os.listdir(source_folder) if os.path.isfile(os.path.join(source_folder, f))]

    for i in range(len(image_names)):
        duplicate_evaluation = check_if_duplicate_image(source_folder, image_names[i], hash_map)
        if duplicate_evaluation is None:
            broken_images.append(image_names[i])
            continue;
        
        if (duplicate_evaluation["duplicate"]):
            duplicate_images[duplicate_evaluation["image_name"]] = duplicate_evaluation["image_hash"]
        elif duplicate_evaluation:
            hash_map[duplicate_evaluation["image_hash"]] = image_names[i]

    for i in range(len(image_names)):
        print("Processing image: " + image_names[i])
        duplicate_evaluation = check_if_duplicate_image(source_folder, image_names[i], hash_map)
        if duplicate_evaluation is None:
            broken_images.append(image_names[i])
            continue;
        if (duplicate_evaluation["duplicate"]):
            duplicate_images[duplicate_evaluation["image_name"]] = duplicate_evaluation["image_hash"]
        elif duplicate_evaluation:
            hash_map[duplicate_evaluation["image_hash"]] = image_names[i]

    # double check if the hash for the duplicates exist, otherwise add them to the manual check duplicates
    updated_duplicate_images, manual_check_duplicates = verify_duplicates(duplicate_images, hash_map)
    print("Duplicates paths: " + str(updated_duplicate_images))
    print("Files to manually check for duplicates: " + str(manual_check_duplicates))

    move_files(source_folder, manual_check_duplicates, manual_check_duplicates_folder)
    move_files(source_folder, broken_images, broken_photos_folder)
    move_files(source_folder, updated_duplicate_images, duplicate_photos_folder)


def create_file_name(image_date, image_time, file_geo_data):
    if (file_geo_data != ""):
        return file_geo_data["country_code"] + "_" + image_date + "_" + image_time
    else:
        return image_date + "_" + image_time

def rename_file(path, original_name, new_name):
    file_extension = original_name.split(".")[1]

    old_path = os.path.join(path, original_name)
    new_path = os.path.join(path, new_name + "." + file_extension)
    
    
    os.rename(old_path, new_path)

    print(original_name + " renamed to -> " + new_name)


def rename_folder(path, original_name, new_name):
    old_path = os.path.join(path, original_name)
    new_path = os.path.join(path, new_name)
    os.rename(old_path, new_path)
    print(original_name + " folder renamed to -> " + new_name)

def get_media_created(video_path):
    print(video_path)
    probe = ffmpeg.probe(video_path)
    if 'format' in probe and 'tags' in probe['format']:
        media_created = probe['format']['tags'].get('creation_time')
        return media_created
    else:
        return None
    
def create_datetime_and_country_folder(parent_folder_path, datetime, country):
    folder_name = datetime + "_" + country
    folder_path = os.path.join(parent_folder_path, folder_name)
    os.mkdir(folder_path)
    print("New folder created in path: " + folder_path)


def update_datetime_and_country_folder(parent_folder_path, original_folder_name, country):
    folder_parts = original_folder_name.split("_")
    if (len(folder_parts) > 2):
        countries = folder_parts[-1].split(",")
        if country in countries:
            return
        else:
            new_folder_name = original_folder_name + "," + country
    else:
        new_folder_name = original_folder_name + "_" + country
    rename_folder(parent_folder_path, original_folder_name, new_folder_name)
                    

def move_file_to_specific_datetime_folder(source_folder, parent_target_folder, file_name, file_date, file_country):
    file_year_month = file_date[0:6]
    folder_names = [f for f in os.listdir(parent_target_folder) if os.path.isdir(os.path.join(parent_target_folder, f))]
    if (len(folder_names) > 0):
        for folder_name in folder_names:
            folder_year_month = folder_name.split("_")[0] + folder_name.split("_")[1]
            if folder_year_month == file_year_month:
                target_folder = os.path.join(parent_target_folder, folder_name)
                move_files(source_folder, [file_name], target_folder)
                update_datetime_and_country_folder(parent_target_folder, folder_name, file_country)
                return
    
    folder_date = file_date[0:4] + "_" +  file_date[4:6]
    folder_name = file_date[0:4] + "_" +  file_date[4:6] + "_" + file_country
    create_datetime_and_country_folder(parent_target_folder, folder_date, file_country)
    target_folder = os.path.join(parent_target_folder, folder_name)
    move_files(source_folder, [file_name], target_folder)
              

def sort_pictures_into_folders(source_folder, target_folder):

    file_names = [f for f in os.listdir(source_folder) if os.path.isfile(os.path.join(source_folder, f))]

    i = 0
    for file_name in file_names:
        print(file_name)

        try:
            check_file_name_changed = file_name.split("_")
            if len(check_file_name_changed) == 3:
                file_split = file_name.split("_")
                file_date = file_split[1]
                file_country = file_split[0]
                move_file_to_specific_datetime_folder(source_folder, target_folder, file_name, file_date, file_country)
                continue

            file_path = os.path.join(source_folder, file_name)
            
            image_data = extract_exif(file_path)
            if (image_data == None):
                print("Skipping since metadata is not found")
                #new_file_name = create_file_name(file_date, file_time, "")
            
            else:
                image_datetime = image_data["DateTime"]
                file_date = (image_datetime.split(" "))[0].replace(":", "")
                file_time = (image_datetime.split(" "))[1].replace(":", "")
                image_gps = extract_image_gps_info(file_path)
                print("File GPS data: " + str(image_gps))

                image_geo_data = get_data_from_geocode(image_gps)
                print(image_geo_data)

                new_file_name = create_file_name(file_date, file_time, image_geo_data)

            
            rename_file(source_folder, file_name, new_file_name)
            move_file_to_specific_datetime_folder(source_folder, target_folder, new_file_name, file_date, file_country)

        except Exception as e:
            print(f"Error processing file {file_name}: {e}") 
        

if __name__ == "__main__":
    # Load config
    config = configparser.ConfigParser()
    config.read('config.ini')

    pillow_heif.register_heif_opener() # opener for .heic files


    # get all the folder configurations
    source_folder = config['Folders']['source_folder']
    sorted_photos_folder = config['Folders']['sorted_photos_folder']
    duplicate_photos_folder = config["Folders"]["duplicate_photos_folder"]
    broken_photos_folder = config["Folders"]["broken_photos_folder"]
    manual_check_duplicates_folder = config["Folders"]["manual_check_duplicates_folder"]

    # example file path for testing
    example_file_path = config["Files"]["example_file_path"]

    # Dictionary to map image hashes to their file names
    hash_map = defaultdict(list)
    duplicate_images = {}
    broken_images = [] # images that either couldn't be processed or cannot be identified as duplicates

    # Sort duplicates into specified folders
    #sort_duplicates(source_folder, manual_check_duplicates_folder, broken_photos_folder, duplicate_photos_folder)

    sort_pictures_into_folders(source_folder, sorted_photos_folder)

    #print(get_media_created(example_file_path))