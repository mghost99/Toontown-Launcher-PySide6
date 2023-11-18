import bz2
import hashlib
import logging
import os
import platform
import threading

import requests
from panda3d.core import Filename, Multifile, VirtualFileSystem
from PySide6.QtCore import QObject, Signal, Slot, QThread

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

class Updater(QObject):
    update_progress_signal = Signal(int)
    update_status_signal = Signal(str)
    update_status_error_signal = Signal(str)
    finished = Signal()
    should_stop = False
    def __init__(
        self, base_url, save_directory="./game/"
    ):
        super().__init__()
        self.update_thread = None
        self.base_url = base_url
        self.version_info_file = "patcher.ver"
        self.save_directory = save_directory
        if not self.save_directory.endswith(os.sep):
            self.save_directory += os.sep
        if not os.path.isdir(self.save_directory):
            os.mkdir(self.save_directory)
        self.env_vars = [
            "GAME_WHITELIST_URL",
            "GAME_IN_GAME_NEWS_URL",
            "GAME_SERVER",
            "ACCOUNT_SERVER",
            "PANDA_DOWNLOAD_URL",
            "PATCHER_BASE_URL_HEAVY_LIFTING",
        ]

    def set_environment_variables(self, content_lines):
        for line in content_lines:
            key, sep, value = line.partition("=")
            if key in self.env_vars:
                try:
                    if key == "PATCHER_BASE_URL_HEAVY_LIFTING":
                        key = "DOWNLOAD_SERVER"
                    os.environ[key] = value
                    logging.info(f"Set environment variable: {key} = {value}")
                except OSError as e:
                    logging.error(
                        f"Failed to set environment variable: {key} = {value}. Error: {e}"
                    )

    def verify_file_hash(self, file_path, expected_hash, expected_size):
        if not os.path.exists(file_path) or os.path.getsize(file_path) != expected_size:
            return False
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest() == expected_hash

    def extract_multifile(self, multifile_path, extract_to):
        vfs = VirtualFileSystem.getGlobalPtr()
        multifile = Multifile()
        multifile.openRead(Filename.fromOsSpecific(os.path.join(self.save_directory, multifile_path)))
        for i in range(multifile.getNumSubfiles()):
            subfile_name = multifile.getSubfileName(i)
            if platform.system() == "Linux" and subfile_name in ["libpandadx8.dll", "libpandadx9.dll"]:
                continue
            else:
                target_path = os.path.join(extract_to, subfile_name)
                print(f"Extracting: {subfile_name} to {target_path}")
                multifile.extractSubfile(i, Filename.fromOsSpecific(target_path))

    def download_and_extract_files(self, content_lines):
        total_files = len(
            [
                line
                for line in content_lines
                if line.startswith("REQUIRED_INSTALL_FILES")
            ]
        )
        current_file = 0
        for line in content_lines:
            if line.startswith("REQUIRED_INSTALL_FILES"):
                files_info = line.split("=")[1].split()
                for file_info in files_info:
                    file_name, file_type = file_info.split(":")
                    if "OSX" in file_name and platform.system() != "Darwin":
                        continue
                    if "LINUX" in file_name and platform.system() != "Linux":
                        continue
                    current_file += 1
                    version_key = f"FILE_{file_name}.current"
                    version_line = next(
                        (l for l in content_lines if l.startswith(version_key)), None
                    )
                    if version_line:
                        version = version_line.split("=")[1]
                        file_url = os.path.join(
                            self.base_url, f"{file_name}.{version}.bz2"
                        )
                        file_hash_info = next(
                            (
                                l
                                for l in content_lines
                                if l.startswith(f"FILE_{file_name}.{version}")
                            ),
                            None,
                        )
                        if file_hash_info:
                            _, size_and_hash = file_hash_info.split("=")
                            expected_size, expected_hash = size_and_hash.split(" ")

                            expected_size = int(expected_size)
                            decompressed_file_path = os.path.join(self.save_directory, f"{file_name}")
                            if self.verify_file_hash(
                                decompressed_file_path, expected_hash, expected_size
                            ):
                                logging.info(
                                    f"File {file_name} already exists and has the correct hash."
                                )
                                continue
                        response = requests.get(file_url, stream=True)
                        total_size = int(response.headers.get("content-length", 0))
                        self.update_status_signal.emit(f"Updating files {current_file}/{total_files}")
                        if response.status_code == 200:
                            logging.info(f"Downloading file: {file_name}.{version}.bz2")
                            file_path = os.path.join(self.save_directory, f"{file_name}.{version}.bz2")
                            with open(file_path, "wb") as file:
                                downloaded_size = 0
                                for data in response.iter_content(chunk_size=4096):
                                    downloaded_size += len(data)
                                    file.write(data)
                                    self.update_progress_signal.emit(int(downloaded_size * 100 / total_size))
                            with bz2.open(file_path, "rb") as f:
                                decompressed_content = f.read()
                            decompressed_file_path = os.path.join(self.save_directory, f"{file_name}")
                            with open(decompressed_file_path, "wb") as f:
                                f.write(decompressed_content)
                                logging.info(f"Decompressed file: {file_name}")
                                phase_1 = "phase_1.mf"
                                phase_2 = "phase_2.mf"
                                if file_name in [phase_1, phase_2]:
                                    self.extract_multifile(f"{file_name}", self.save_directory)
                            os.remove(file_path)
                            logging.info(
                                f"Removed compressed file: {file_name}.{version}.bz2"
                            )
                        else:
                            self.update_status_error_signal.emit(f"Failed to download {file_name}")

    @Slot()
    def start_update(self):
        update_thread = threading.Thread(target=self.update)
        update_thread.start()

    @Slot()
    def update(self):
        try:
            if not self.should_stop:
                content_lines = self.fetch_version_info()
                self.set_environment_variables(content_lines)
                self.download_and_extract_files(content_lines)
                self.cleanup()
            self.update_status_signal.emit("Have fun playing Toontown!")
        except Exception as e:
            self.update_status_error_signal.emit(f"An error occurred during the update process.")
            logging.error(f"An error occurred during the update process: {e}")
        finally:
            self.finished.emit()

    @Slot()
    def stop(self):
        self.should_stop = True

    def fetch_version_info(self):
        response = requests.get(self.base_url + self.version_info_file)
        if response.status_code == 200:
            logging.info("Successfully fetched version info.")
            return response.text.splitlines()
        else:
            logging.error("Failed to connect to the update server.")
            return []

    def cleanup(self):
        hash_data = os.path.join(self.save_directory, "hash_data")
        if os.path.exists(hash_data):
            if os.path.isfile(hash_data):
                os.remove(hash_data)
                os.mkdir(hash_data)
                logging.info("Removed hash_data file and created an empty directory.")
        else:
            os.mkdir(hash_data)
            logging.info("hash_data file or folder not found; creating empty directory.")