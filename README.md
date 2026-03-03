Made with Python and Libcotd

Instructions for running with python:
- Clone this Repository and export it as the folder "solo-shipping"
- Open a terminal and move into the directory "solo-shipping"
- Install python 3.12 on your system
- Set up a virtual environment, depending on your platform.

MacOS/Linux:
-  python3.12 -m venv venv
-  source venv/bin/activate
-  pip install -r requirements.txt

Windows:
-  python3.12 -m venv venv
-  venv/Scripts/activate.bat
-  pip install -r requirements.txt

Running the game:
- Now that all the requirements are installed, run the game with: python main.py

Instructions for Building from Source:
- These instructions are only needed if you want to bundle the game into an executable yourself
- Once you confirm the above is working you'll want to install pyinstaller
- pip install pyinstaller
- Then run the following command depending on your platform.

MacOS/Linux:
- pyinstaller --onefile --add-data "dejavu10x10_gs_tc.png:." --add-data "dialogue:dialogue" --add-data "sounds:sounds" main.py

Windows:
- pyinstaller --onefile --noconsole --collect-all pygame --collect-all tcod --collect-all cffi --collect-all numpy --hidden-import=_cffi_backend --add-binary "C:\Users\anfer\Documents\GitHub\solo-shipping\venv\Lib\site-packages_cffi_backend.cp312-win_amd64.pyd;." --add-data "dejavu10x10_gs_tc.png;." --add-data "dialogue:dialogue" --add-data "sounds;sounds" main.py
