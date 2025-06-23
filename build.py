from datetime import datetime
import os
import time
import zipfile
import shutil
from pathlib import Path
import requests
from circup.commands import main as circup_cli

# TODO: maybe change these to use the first URLs i.e. https://learn.adafruit.com/elements/3198279/download?type=zip
#  instead of the redirect URLs that are direct to the CDN. That will make easier for users to add apps here.
#  The code will need to follow the redirect and get the filename from the next URL.
LEARN_PROJECT_URLS = [
    "https://cdn-learn.adafruit.com/downloads/zip/3194974/Metro/Metro_RP2350_Snake.zip?timestamp={}",
    "https://cdn-learn.adafruit.com/downloads/zip/3195762/Metro/Metro_RP2350_Memory/memory_game.zip?timestamp={}",
    "https://cdn-learn.adafruit.com/downloads/zip/3195805/Metro/Metro_RP2350_CircuitPython_Matrix.zip?timestamp={}",
    "https://cdn-learn.adafruit.com/downloads/zip/3194658/Metro/Metro_RP2350_FlappyNyanCat.zip?timestamp={}",
    "https://cdn-learn.adafruit.com/downloads/zip/3196927/Metro/Metro_RP2350_Match3/match3_game.zip?timestamp={}",
    "https://cdn-learn.adafruit.com/downloads/zip/3194422/Metro/Metro_RP2350_Breakout.zip?timestamp={}",
    "https://cdn-learn.adafruit.com/downloads/zip/3196755/Metro/Metro_RP2350_Chips_Challenge.zip?timestamp={}",
    "https://cdn-learn.adafruit.com/downloads/zip/3198116/Metro/Metro_RP2350_Minesweeper.zip?timestamp={}",
    "https://cdn-learn.adafruit.com/downloads/zip/3198279/Fruit_Jam/Larsio_Paint_Music.zip?timestamp=1750522464"
]

def create_font_specific_zip(font_path: Path, src_dir: Path, learn_projects_dir: Path, output_dir: Path):
    # Get font name without extension
    font_name = font_path.stem
    
    # Create output zip filename
    output_zip = output_dir / f"fruit_jam_{font_name}.zip"
    
    # Create a clean temporary directory for building the zip
    temp_dir = output_dir / "temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)
    
    try:
        # Copy src contents
        shutil.copytree(src_dir, temp_dir, dirs_exist_ok=True)
        
        # Create fonts directory and copy the specific font
        fonts_dir = temp_dir / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(font_path, fonts_dir / "terminal.lvfontbin")
        
        # Extract learn-projects contents into apps directory
        apps_dir = temp_dir / "apps"
        apps_dir.mkdir(parents=True, exist_ok=True)
        for zip_path in learn_projects_dir.glob("*.zip"):
            # Create app-specific directory using zip name without extension
            app_name = zip_path.stem
            app_dir = apps_dir / app_name
            app_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract zip contents and process them
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Find the directory containing code.py
                code_dir = None
                for path in zf.namelist():
                    if path.endswith('/code.py'):
                        code_dir = str(Path(path).parent) + '/'
                        break
                
                if not code_dir:
                    print(f"Warning: No code.py found in {zip_path}")
                    continue
                
                # Extract files from the code.py directory to app directory
                for path in zf.namelist():
                    if path.startswith(code_dir):
                        # Skip the lib directory as we'll handle it separately
                        if 'lib/' in path:
                            continue
                        if path.endswith("/"):
                            # skip directories, they will get created by
                            # mkdir(parents=True) below
                            continue
                        
                        # Get the relative path from code_dir
                        rel_path = path[len(code_dir):]
                        if rel_path:
                            # Extract the file
                            source = zf.open(path)
                            target = app_dir / rel_path
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with open(target, 'wb') as f:
                                f.write(source.read())
                
                # Handle lib directory specially - move to root
                for path in zf.namelist():
                    if '/lib/' in path:
                        # Get the part of the path after 'lib/'
                        lib_index = path.index('/lib/') + 5  # skip past '/lib/'
                        rel_path = path[lib_index:]
                        
                        # Skip directory entries
                        if not rel_path or path.endswith('/'):
                            continue
                            
                        # Extract the file to root lib directory
                        source = zf.open(path)
                        target = temp_dir / 'lib' / rel_path
                        # Ensure parent directory exists
                        target.parent.mkdir(parents=True, exist_ok=True)
                        # Write the file
                        with open(target, 'wb') as f:
                            f.write(source.read())

        # copy builtin apps
        shutil.copytree("builtin_apps", apps_dir, dirs_exist_ok=True)
        shutil.copyfile("mock_boot_out.txt", temp_dir / "boot_out.txt")

        # install launcher required libs
        circup_cli(["--path", temp_dir, "install", "--auto"],
                   standalone_mode=False)

        # install builtin apps required libs
        for builtin_app_dir in os.listdir("builtin_apps"):
            circup_cli(["--path", temp_dir, "install", "--auto", "--auto-file", f"apps/{builtin_app_dir}/code.py"],
                       standalone_mode=False)
        os.remove(temp_dir / "boot_out.txt")
        # Create the final zip file
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in temp_dir.rglob("*"):
                if file_path.is_file():
                    modification_time = datetime(2000, 1, 1, 0, 0, 0)
                    modification_timestamp = modification_time.timestamp()
                    os.utime(file_path, (modification_timestamp, modification_timestamp))
                    arcname = file_path.relative_to(temp_dir)
                    zf.write(file_path, arcname)
                    
        print(f"Created {output_zip}")
        
    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def download_learn_projects():
    for url in LEARN_PROJECT_URLS:
        response = requests.get(url.format(int(time.time())), allow_redirects=True)
        resp_url = response.url
        #print(resp_url)
        filename = resp_url.split("/")[-1].split("?")[0]
        with open(f"learn-projects/{filename}", 'wb') as f:
            f.write(response.content)


def main():

    # download all learn project zips
    download_learn_projects()

    # Get the project root directory
    root_dir = Path(__file__).parent
    
    # Set up paths
    fonts_dir = root_dir / "fonts"
    src_dir = root_dir / "src"
    learn_projects_dir = root_dir / "learn-projects"
    output_dir = root_dir / "dist"

    # delete output dir if it exists
    if output_dir.exists():
        shutil.rmtree(output_dir)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each font
    for font_path in fonts_dir.glob("*.lvfontbin"):
        create_font_specific_zip(font_path, src_dir, learn_projects_dir, output_dir)

if __name__ == "__main__":
    main()
