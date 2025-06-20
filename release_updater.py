import hashlib
import shutil
from pathlib import Path
from urllib.request import urlretrieve

import requests

from build import main as build_main


def get_file_sha256(file_path):
    """Calculates the SHA256 hash of a file.

    Args:
        file_path: The path to the file.

    Returns:
        The SHA256 hash of the file as a hexadecimal string.
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
    except FileNotFoundError:
        return "File not found."
    return sha256_hash.hexdigest()

def print_hashes(hash_dict):
    for filename in sorted(hash_dict.keys()):
        print(f"{filename}: {hash_dict[filename]}")


def is_release_required():
    """
    Checks if there are new versions of any apps. When new versions exist
    a new release is required.

    :return: True if there are new versions of any apps, and release is required, False otherwise.
    """

    try:
        dl_dir = Path("latest_dl")
        if dl_dir.exists():
            shutil.rmtree("latest_dl")
        dl_dir.mkdir()
    except FileExistsError:
        pass

    # download built zips from most recent release
    RELEASE_API_URL = "https://api.github.com/repos/adafruit/Fruit-Jam-OS/releases?per_page=1"
    latest_release_obj = requests.get(RELEASE_API_URL).json()[0]
    for asset in latest_release_obj["assets"]:
        asset_dl_url = asset["browser_download_url"]
        asset_filename = asset_dl_url.split("/")[-1]
        urlretrieve(asset_dl_url, f"latest_dl/{asset_filename}")

    # get sha256 hashes for each downloaded zip
    downloaded_file_hashes = {}
    for dl_file in Path("latest_dl").iterdir():
        downloaded_file_hashes[dl_file.name] = get_file_sha256(dl_file)

    # make a local build
    build_main()

    # get sha256 hashes for built zips
    dist_file_hashes = {}
    for dist_file in Path("dist").iterdir():
        dist_file_hashes[dist_file.name] = get_file_sha256(dist_file)

    print("Downloaded file hashes:")
    print_hashes(downloaded_file_hashes)

    print("Dist file hashes:")
    print_hashes(dist_file_hashes)

    # compare hashes
    if dist_file_hashes != downloaded_file_hashes:
        print("Zip hashes differ, a release is required.")
        return True

    print("Zip hashes match, no release required.")
    return False


if __name__ == '__main__':
    is_release_required()
