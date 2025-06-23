import hashlib
import shutil
from pathlib import Path
from urllib.request import urlretrieve
import os
import sys
import json
import re
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



def parse_semantic_version(version_string):
    """Parse semantic version string and return (major, minor, patch)."""

    # Match semantic version pattern
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-.*)?(?:\+.*)?$', version_string)
    if not match:
        raise ValueError(f"Invalid semantic version: {version_string}")

    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def increment_patch_version(version_string):
    """Increment patch version by 1."""
    major, minor, patch = parse_semantic_version(version_string)
    new_patch = patch + 1
    return f"{major}.{minor}.{new_patch}"


def get_latest_release():
    """Fetch the latest release from GitHub API."""
    url = f"https://api.github.com/repos/adafruit/Fruit-Jam-OS/releases/latest"
    headers = {
        "Authorization": f"token {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github.v3+json"
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Error fetching latest release: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

    return response.json()


def create_release(tag_name):
    """Create a new GitHub release."""
    url = f"https://api.github.com/repos/adafruit/Fruit-Jam-OS/releases"
    headers = {
        "Authorization": f"token {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }

    data = {
        "tag_name": tag_name,
        "name": tag_name,
        "body": f"Release {tag_name}",
        "draft": False,
        "prerelease": False
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code != 201:
        print(f"Error creating release: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

    return response.json()

if __name__ == '__main__':
    if is_release_required():

        print(f"Creating release for Fruit Jam OS")

        # Get latest release
        latest_release = get_latest_release()

        if latest_release:
            latest_tag = latest_release["tag_name"]
            print(f"Latest release: {latest_tag}")

            try:
                new_tag = increment_patch_version(latest_tag)
            except ValueError as e:
                print(f"Error parsing version: {e}")
                sys.exit(1)
        else:
            new_tag = "0.1.0"

        print(f"Creating new release: {new_tag}")

        new_release = create_release(
            tag_name=new_tag,
        )

        print(f"✅ Successfully created release: {new_tag}")
        print(f"Release URL: {new_release['html_url']}")
