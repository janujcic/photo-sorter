import os
import configparser
import shutil
from PIL import Image, ExifTags
import pillow_heif
from PIL.ExifTags import TAGS, GPSTAGS
import imagehash
from collections import defaultdict
import re
import reverse_geocode
import ffmpeg
from random import randint
from fractions import Fraction
import piexif
from typing import List
import static_ffmpeg
static_ffmpeg.add_paths()

def extract_exif(file_path):

    pillow_heif.register_heif_opener()

    file_extension = os.path.splitext(file_path)[1].lower()

    if file_extension == '.heic':
         # Use pillow-heif for HEIC format
        heif_image = pillow_heif.open_heif(file_path)
        exif_data = heif_image.info.get('exif')
        
        if exif_data:
            # Decode the EXIF bytes using piexif
            exif_dict = piexif.load(exif_data)
        else:
            exif_dict = None

        exif_dict = extract_exif_data(exif_dict)
    else:
         # Use Pillow for other formats
        image = Image.open(file_path)
        exif_data = image._getexif()
        exif_dict = {ExifTags.TAGS.get(tag): value for tag, value in exif_data.items()} if exif_data else None

    # Convert EXIF data to a more readable dictionary format
    return exif_dict

def extract_exif_data(exif_dict):
    result = {}

    # Extract the DateTime
    if '0th' in exif_dict and 306 in exif_dict['0th']:
        result['DateTime'] = exif_dict['0th'][306].decode() if isinstance(exif_dict['0th'][306], bytes) else exif_dict['0th'][306]
    
    # Extract GPS Data
    gps_info = {}
    if 'GPS' in exif_dict:
        gps_data = exif_dict['GPS']

        # Latitude
        if 1 in gps_data and 2 in gps_data:
            latitude_ref = gps_data[1].decode() if isinstance(gps_data[1], bytes) else gps_data[1]
            latitude = [float(Fraction(coord[0], coord[1])) for coord in gps_data[2]]
            latitude = latitude[0] + latitude[1]/60 + latitude[2]/3600
            gps_info['Latitude'] = latitude if latitude_ref == 'N' else -latitude
        
        # Longitude
        if 3 in gps_data and 4 in gps_data:
            longitude_ref = gps_data[3].decode() if isinstance(gps_data[3], bytes) else gps_data[3]
            longitude = [float(Fraction(coord[0], coord[1])) for coord in gps_data[4]]
            longitude = longitude[0] + longitude[1]/60 + longitude[2]/3600
            gps_info['Longitude'] = longitude if longitude_ref == 'E' else -longitude

        # Altitude
        if 5 in gps_data and 6 in gps_data:
            altitude = float(Fraction(gps_data[6][0], gps_data[6][1]))
            gps_info['Altitude'] = altitude if gps_data[5] == 0 else -altitude
    
    # Include GPS info in the result if available
    if gps_info:
        result['GPS'] = gps_info
    
    return result

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

def move_file_to_folder(source: str, destination: str):
    """Move a file from the source path to the destination path."""
    try:
        shutil.move(source, destination)
        print(f"Moved file: {source} to {destination}")
    except Exception as e:
        print(f"Error moving {source} to {destination}: {e}")

def handle_existing_file(existing_file: str, new_file: str, duplicate_folder: str, target_folder: str, existing_is_higher_quality: bool):
    """Handle cases where a file with the same name but different extension exists."""
    existing_file_name = os.path.basename(existing_file)  # Extract just the file name

    if existing_is_higher_quality:
        if duplicate_folder:
            duplicate_path = os.path.join(duplicate_folder, os.path.basename(new_file))
            move_file_to_folder(new_file, duplicate_path)
            print(f"Higher quality file {existing_file} already exists in {target_folder}. Copying to {duplicate_path}.")
            return True
        print(f"Higher quality file {existing_file} already exists in {target_folder}. Skipping {new_file}.")
        return True
    else:
        if duplicate_folder:
            duplicate_path = os.path.join(duplicate_folder, existing_file_name)
            print(f"Existing folder {duplicate_path}")
            move_file_to_folder(existing_file, duplicate_path)
            print(f"Existing file {existing_file} is lower quality in {target_folder}. Moving it to: {duplicate_path}.")
        else:
            os.remove(existing_file)
        return False

def move_files(source_folder: str, file_names: List[str], target_folder: str, duplicate_folder: str = ""):
    """Move files from source to target folder, handling duplicates based on file quality."""
    quality_priority = ['.heic', '.jpeg', '.jpg']

    for file_name in file_names:
        file_base, file_ext = os.path.splitext(file_name)
        file_ext = file_ext.lower()

        source_path = os.path.join(source_folder, file_name)
        destination_path = os.path.join(target_folder, file_name)

        moved_to_duplicate = False

        # Check for existing files with different extensions in the target folder
        for ext in quality_priority:
            if ext != file_ext:
                alt_file_name = f"{file_base}{ext}"
                alt_file_path = os.path.join(target_folder, alt_file_name)

                if os.path.exists(alt_file_path):
                    is_higher_quality = quality_priority.index(file_ext) > quality_priority.index(ext)
                    moved_to_duplicate = handle_existing_file(
                        alt_file_path, source_path, duplicate_folder, target_folder, is_higher_quality
                    )
                    if moved_to_duplicate:
                        break

        if moved_to_duplicate:
            continue

        # Check if the exact file already exists in the target folder
        if os.path.exists(destination_path):
            if duplicate_folder:
                duplicate_path = os.path.join(duplicate_folder, file_name)
                print(f"File {file_name} already exists in {target_folder}. Moving to duplicate folder.")
                move_file_to_folder(source_path, duplicate_path)
            else:
                print(f"File {file_name} already exists in {target_folder}.")
            continue

        # Move the file to the target folder
        move_file_to_folder(source_path, destination_path)

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
            print(f"Error moving {file_path} to {destination_path}: {e}")

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

    old_path = os.path.join(path, original_name)
    
    
    if ("." in original_name):
        file_extension = original_name.split(".")[1]
        new_name += "." + file_extension
    
    new_path = os.path.join(path, new_name)
    
    print(old_path)
    print(new_path)
    os.rename(old_path, new_path)

    print(original_name + " renamed to -> " + new_name)
    return new_name


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
                    

def move_file_to_specific_datetime_folder(source_folder, parent_target_folder, file_name, file_date, file_country, duplicate_folder=""):
    file_year_month = file_date[0:6]
    folder_names = [f for f in os.listdir(parent_target_folder) if os.path.isdir(os.path.join(parent_target_folder, f))]
    if (len(folder_names) > 0):
        for folder_name in folder_names:
            folder_year_month = folder_name.split("_")[0] + folder_name.split("_")[1]
            if folder_year_month == file_year_month:
                current_folder_path = os.path.join(parent_target_folder, folder_name)
                if (file_country == ""):
                    # find something taken on the same day and use that country
                    subfolder_files = [f for f in os.listdir(current_folder_path) if os.path.isfile(os.path.join(current_folder_path, f))]
                    for subfolder_file in subfolder_files:
                        existing_file_date = subfolder_file.split("_")[1]
                        if file_date == existing_file_date:
                            same_day_file_country = subfolder_file.split("_")[0]
                            new_file_name = same_day_file_country + "_" + file_name
                            new_file_name = rename_file(source_folder, file_name, new_file_name)
                           
                            move_files(source_folder, [new_file_name], current_folder_path, duplicate_folder)
                            return

                    move_files(source_folder, [file_name], current_folder_path, duplicate_folder) # no similar file made on that day, don't use the country
 

                else:
                    target_folder = os.path.join(parent_target_folder, folder_name)
                    move_files(source_folder, [file_name], target_folder, duplicate_folder)
                    update_datetime_and_country_folder(parent_target_folder, folder_name, file_country)
                return
    
    folder_date = file_date[0:4] + "_" +  file_date[4:6]
    folder_name = file_date[0:4] + "_" +  file_date[4:6] + "_" + file_country
    create_datetime_and_country_folder(parent_target_folder, folder_date, file_country)
    target_folder = os.path.join(parent_target_folder, folder_name)
    move_files(source_folder, [file_name], target_folder, duplicate_folder)




def sort_pictures_into_folders(source_folder, target_folder, duplicate_folder="", unsorted_folder=""):

    file_names = [f for f in os.listdir(source_folder) if os.path.isfile(os.path.join(source_folder, f))]

    i = 0
    for file_name in file_names:

        try:
            check_file_name_changed = file_name.split("_")
            # if the file already has the correct name, then just move it {Country Code}_{YYYYMMDD}_{HH:MM:SS}
            if len(check_file_name_changed) == 3:
                file_split = file_name.split("_")
                file_date = file_split[1]
                file_country = file_split[0]
                move_file_to_specific_datetime_folder(source_folder, target_folder, file_name, file_date, file_country, duplicate_folder)
                continue
            file_path = os.path.join(source_folder, file_name)
            file_extension = os.path.splitext(file_path)[1].lower()

            # processing for videos
            if (file_extension == ".mov" or file_extension == ".mp4" or file_extension == ".mp3"):
                print(file_name)
                video_data = get_media_created(file_path)
                video_date = video_data.split("T")[0].replace("-", "")
                video_time = ((video_data.split("T")[1]).split(".")[0]).replace(":", "")
                new_video_name = create_file_name(video_date, video_time, "")
                print("File name: " + file_name)
                new_video_name = rename_file(source_folder, file_name, new_video_name)
                move_file_to_specific_datetime_folder(source_folder, target_folder, new_video_name, video_date, "", duplicate_folder)
                continue
            
            image_data = extract_exif(file_path)

            if image_data == None:
                move_files(source_folder, [file_name], unsorted_folder, duplicate_folder)
                continue

            elif (file_extension == ".heic"):
                image_datetime = image_data["DateTime"]
                file_date = (image_datetime.split(" "))[0].replace(":", "")
                file_time = (image_datetime.split(" "))[1].replace(":", "")
                image_gps = (image_data["GPS"]["Latitude"], image_data["GPS"]["Longitude"])
                image_geo_data = get_data_from_geocode(image_gps)
                new_file_name = create_file_name(file_date, file_time, image_geo_data)
            
            else:
                image_datetime = image_data["DateTime"]
                file_date = (image_datetime.split(" "))[0].replace(":", "")
                file_time = (image_datetime.split(" "))[1].replace(":", "")
                image_gps = extract_image_gps_info(file_path)
                image_geo_data = get_data_from_geocode(image_gps)
                new_file_name = create_file_name(file_date, file_time, image_geo_data)

            file_country = image_geo_data["country_code"]
            new_file_name = rename_file(source_folder, file_name, new_file_name)
            move_file_to_specific_datetime_folder(source_folder, target_folder, new_file_name, file_date, file_country, duplicate_folder)

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
    unsorted_folder = config["Folders"]["unsorted_folder"]

    # example file path for testing
    example_file_path = config["Files"]["example_file_path"]

    # Sort duplicates into specified folders
    #sort_duplicates(source_folder, manual_check_duplicates_folder, broken_photos_folder, duplicate_photos_folder)

    sort_pictures_into_folders(source_folder, sorted_photos_folder, duplicate_photos_folder, unsorted_folder)

    #print(extract_exif(example_file_path))