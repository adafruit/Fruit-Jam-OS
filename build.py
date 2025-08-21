from datetime import datetime
import os
import zipfile
import shutil
from pathlib import Path
from circup.commands import main as circup_cli


# each path is a tuple that contains:
# (path within learn repo, directory name to use inside of apps/)
LEARN_PROJECT_PATHS = [
    ("Metro/Metro_RP2350_Snake/","Metro_RP2350_Snake"),
    ("Metro/Metro_RP2350_Memory/memory_game/", "Metro_RP2350_Memory"),
    ("Metro/Metro_RP2350_CircuitPython_Matrix/", "Metro_RP2350_CircuitPython_Matrix"),
    ("Metro/Metro_RP2350_FlappyNyanCat/", "Metro_RP2350_FlappyNyanCat"),
    ("Metro/Metro_RP2350_Match3/match3_game/", "Metro_RP2350_Match3"),
    ("Metro/Metro_RP2350_Breakout/", "Metro_RP2350_Breakout"),
    ("Metro/Metro_RP2350_Chips_Challenge/", "Metro_RP2350_Chips_Challenge"),
    ("Metro/Metro_RP2350_Minesweeper/", "Metro_RP2350_Minesweeper"),
    ("Fruit_Jam/Larsio_Paint_Music/", "Larsio_Paint_Music"),
    ("Fruit_Jam/Fruit_Jam_IRC_Client/", "Fruit_Jam_IRC_Client"),
    ("Fruit_Jam/Fruit_Jam_PyPaint/", "Fruit_Jam_PyPaint"),
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
        # remove empty __init__.py file
        os.remove(temp_dir / "__init__.py")
        
        # Create fonts directory and copy the specific font
        fonts_dir = temp_dir / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(font_path, fonts_dir / "terminal.lvfontbin")
        
        # Extract learn-projects contents into apps directory
        apps_dir = temp_dir / "apps"
        apps_dir.mkdir(parents=True, exist_ok=True)
        # copy learn apps
        for learn_app_path, dir_name in LEARN_PROJECT_PATHS:
            shutil.copytree(f"Adafruit_Learning_System_Guides/{learn_app_path}", apps_dir / dir_name, dirs_exist_ok=True)

        # copy builtin apps
        shutil.copytree("builtin_apps", apps_dir, dirs_exist_ok=True)
        shutil.copyfile("mock_boot_out.txt", temp_dir / "boot_out.txt")

        # install launcher required libs
        circup_cli(["--path", temp_dir, "install", "--auto"],
                   standalone_mode=False)

        # install apps required libs
        for app_dir in os.listdir(apps_dir):
            circup_cli(["--path", temp_dir, "install", "--auto", "--auto-file", f"apps/{app_dir}/code.py"],
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
    try:
        shutil.rmtree("Adafruit_Learning_System_Guides/")
    except FileNotFoundError:
        pass

    os.system("git clone https://github.com/adafruit/Adafruit_Learning_System_Guides.git")


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
