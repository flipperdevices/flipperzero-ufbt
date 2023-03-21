# uFBT - micro Flipper Build Tool

uFBT is a tool for building applications for Flipper Zero. It is a simplified version of [Flipper Build Tool (FBT)](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/documentation/fbt.md). 

uFBT allows you to perform basic development tasks for Flipper Zero, like building and debugging applications, flashing firmware. It uses prebuilt binaries and libraries, so you don't need to build the whole firmware to compile and debug your application.


## Installation

Clone this repository and add its path to your `PATH` environment variable. On first run, uFBT will download and install all required SDK components from `dev` branch of official firmware.

### Updating the SDK

To update the SDK, run `ufbt update`. This will download and install all required SDK components from previously used channel or branch.

To switch to a different version of the SDK, run `ufbt update --channel=[dev|rc|release]`. Or you can use any not-yet-merged branch from official repo, like `ufbt update --branch=feature/my-awesome-feature`.

If something goes wrong and uFBT state becomes corrupted, you can reset it by running `ufbt purge`. If that doesn't work, you can try removing `.ufbt` subfolder manually from your home folder.

## Usage

### Building & running your application

Run `ufbt` in the root directory of your application (the one with `application.fam` file in it). It will build your application and place the resulting binary in `dist` subdirectory.

You can upload and start your application on Flipper attached over  USB using `ufbt launch`.

### Debugging

In order to debug your application, you need to be running the firmware distributed alongside with current SDK version. You can flash it to your Flipper using `ufbt flash` (over ST-Link), `ufbt flash_usb` (over USB) or `ufbt flash_blackmagic` (using Wi-Fi dev board running Blackmagic firmware).

You can attach to running firmware using `ufbt debug` (for ST-Link) or `ufbt blackmagic` (for Wi-Fi dev board).

### VSCode integration

uFBT provides a configuration for VSCode that allows you to build and debug your application directly from the IDE. To deploy it, run `ufbt vscode_dist` in the root directory of your application. Then you can open the project in VSCode (`File`-`Open Folder...`) and use the provided launch (`ctrl+shift+b`) & debugging (`ctrl+shift+d`) configurations.

### Application template

uFBT can create a template for your application. To do this, run `ufbt create APPID=<app_id>` in the directory where you want to create your application. It will create an application manifest and its main source file. You can then build and debug your application using the instructions above.
Application manifests are explained in the [FBT documentation](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/documentation/AppManifests.md).

### Other

 * `ufbt cli` starts a CLI session with the device;
 * `ufbt lint`, `ufbt format` run clang-format on application's sources.
