# Kodi Linux Binary Add-ons Repository

Pre-compiled **Linux** binary add-ons (PVR clients, inputstreams, decoders, screensavers, visualizations) for Kodi.

## Repository Downloads

| Renderer | `amd64` (x86_64 Linux) | `aarch64` (ARM64 Linux) |
| :--- | :--- | :--- |
| **`gl`** | [repository.binaryaddons-gl-amd64.zip](https://github.com/hbiyik/kodi-binary-addons-repo/releases/download/repos/repository.binaryaddons-gl-amd64.zip) | [repository.binaryaddons-gl-aarch64.zip](https://github.com/hbiyik/kodi-binary-addons-repo/releases/download/repos/repository.binaryaddons-gl-aarch64.zip) |
| **`gles`** | [repository.binaryaddons-gles-amd64.zip](https://github.com/hbiyik/kodi-binary-addons-repo/releases/download/repos/repository.binaryaddons-gles-amd64.zip) | [repository.binaryaddons-gles-aarch64.zip](https://github.com/hbiyik/kodi-binary-addons-repo/releases/download/repos/repository.binaryaddons-gles-aarch64.zip) |

## Choosing Between `gl` and `gles`

- **`gl` (Desktop OpenGL):** Standard for desktop Linux installations using standard GPUs.
- **`gles` (OpenGL ES):** Used for single-board computers (SBCs) or Linux setups compiled with GLES rendering.

## Installing in Kodi

Before installing, open **Kodi** on your Linux system, go to **Settings** (gear icon) → **System** → **Add-ons**, and enable **Unknown sources**.

### Method 1: Install via Kodi File Source (Recommended)

Add the repository index directly as an HTTP source in Kodi so you can browse and install the matching repository `.zip` straight from the index without downloading it separately first.

1. Go to **Settings** (gear icon) → **File manager** → **Add source**.
2. Select `<None>` and enter the following URL:
   ```text
   https://kodi-binary-addons-repo.boogiepop.workers.dev/
   ```
3. Enter a name for the media source (e.g., `binary-addons`) and select **OK**.
4. Return to the main menu and select **Add-ons** → **Install from zip file** (or click the open-box icon at the top of the Add-ons menu).
5. Select your newly added source (`binary-addons`) and choose the `.zip` entry matching your rendering engine (`gl` or `gles`) and architecture (`amd64` or `aarch64`) (e.g., `repos/repository.binaryaddons-gl-amd64.zip`).
6. After the notification confirms the repository was installed, select **Install from repository**.
7. Select the newly added binary add-ons repository to browse and install your desired binary add-ons.

### Method 2: Download and Install `.zip` Manually

Download the repository `.zip` file directly to your device from the release table and install it from local storage.

1. Download the repository `.zip` file for your architecture (`amd64` or `aarch64`) and rendering engine (`gl` or `gles`) from the **Repository Downloads** table above.
2. Return to the Kodi main menu and select **Add-ons** → **Install from zip file** (or click the open-box icon at the top of the Add-ons menu).
3. Browse to your local storage (e.g., your `Downloads` directory) and select the downloaded `repository.binaryaddons-<renderer>-<arch>.zip` file (e.g., `repository.binaryaddons-gl-amd64.zip`).
4. After the notification confirms the repository was installed, select **Install from repository**.
5. Select the newly added binary add-ons repository to browse and install your desired binary add-ons.