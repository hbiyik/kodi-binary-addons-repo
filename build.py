"""
 Copyright (C) 2026 boogie

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import json
import sys
import os
import subprocess
import logging
import shutil
import multiprocessing
import zipfile
import hashlib

import xml.etree.ElementTree as ET


GITHASHLEN = 6
ADDONHISTORY = 5
KODI = "kodi"
ADDONS = "addons"

# Result states for buildaddon()
BUILT = "built"
SKIPPED = "skipped"
FAILED = "failed"


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(funcName)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def loadconfig(path):
    with open(path) as fp:
        return json.load(fp)


def parseaddonversion(fname):
    """Parse '<kodirev>.<addonrev>.<kodihash>.<addonhash>[.zip]' into a tuple."""
    if fname.endswith(".zip"):
        fname = fname[:-4]
    vers = fname.split(".")
    if len(vers) < 4:
        raise ValueError(f"Unexpected addon version format: {fname!r}")
    kodirev, addonrev, kodihash, addonhash = vers[-4:]
    return (int(kodirev), int(addonrev), kodihash, addonhash)


def existingversions(repodir, addonname):
    """Return the set of versions of addonname currently listed in addons.xml."""
    versions = set()
    addonsxml = os.path.join(repodir, "addons.xml")
    if not os.path.exists(addonsxml):
        return versions
    try:
        tree = ET.parse(addonsxml)
    except ET.ParseError as e:
        logger.warning("Cannot parse %s: %s", addonsxml, e)
        return versions
    for addon in tree.getroot().findall("addon"):
        if addon.attrib.get("id") != addonname:
            continue
        try:
            versions.add(parseaddonversion(addon.attrib.get("version", "")))
        except ValueError as e:
            logger.warning("Ignoring unparsable version of %s: %s", addonname, e)
    return versions


def run_cmd(*cmd, cwd=None, exitonerror=True, capture=False, env=None):
    cmd_s = " ".join(cmd)
    cwd = cwd or os.getcwd()
    try:
        logger.debug("Running '%s' in %s", cmd_s, cwd)
        res = subprocess.run(
            cmd, cwd=cwd, check=True, capture_output=capture, text=True, env=env
        )
        return 0, (res.stdout.strip() if capture else "")
    except FileNotFoundError as e:
        logger.error("'%s' could not be started: %s", cmd_s, e)
        if exitonerror:
            sys.exit(127)
        return 127, ""
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip() if capture else ""
        if exitonerror:
            logger.error("'%s' in %s exited with %s %s", cmd_s, cwd, e.returncode, stderr)
            sys.exit(e.returncode)
        if stderr:
            logger.debug("'%s' failed: %s", cmd_s, stderr)
        return e.returncode, ""


def checkout(srcdir, name, url, ref, commit=None):
    target_dir = os.path.join(srcdir, name)
    os.makedirs(target_dir, exist_ok=True)

    # Never let git discover a repository above target_dir (e.g. the repo
    # this script lives in).
    genv = os.environ.copy()
    genv["GIT_CEILING_DIRECTORIES"] = os.path.abspath(srcdir)

    def git(*args, **kw):
        return run_cmd("git", *args, cwd=target_dir, env=genv, **kw)

    is_repo = os.path.isdir(os.path.join(target_dir, ".git"))
    current_remote = ""
    if is_repo:
        code, current_remote = git("remote", "get-url", "origin", capture=True, exitonerror=False)
        if code or not current_remote:
            is_repo = False

    if not is_repo:
        shutil.rmtree(target_dir, ignore_errors=True)
        os.makedirs(target_dir, exist_ok=True)
        logger.info("Repository not found at %s. Cloning...", target_dir)
        git("clone", "--filter=tree:0", "-b", ref, url, ".")
    elif current_remote != url:
        logger.info("Updating remote URL to %s...", url)
        git("remote", "set-url", "origin", url)

    def count_commits():
        _, out = git("rev-list", "--count", "HEAD", capture=True)
        return int(out) if out.isdigit() else 0

    _, old_hash = git("rev-parse", "HEAD", capture=True)
    old_count = count_commits()
    old_hash = old_hash[:GITHASHLEN]

    # Works for branches, tags and (where the server allows it) commit hashes.
    git("fetch", "-q", "origin", commit or ref)
    git("reset", "-q", "--hard", "FETCH_HEAD")

    _, final_hash = git("rev-parse", "HEAD", capture=True)
    final_count = count_commits()
    final_hash = final_hash[:GITHASHLEN]

    if old_hash == final_hash:
        logger.info("Repository checked out: %s(%d)", final_hash, final_count)
    else:
        logger.info("Repository updated: %s(%d) -> %s(%d)", old_hash, old_count, final_hash, final_count)

    return final_hash, final_count


def find_addon_roots(install_dir):
    """Directories under install_dir containing addon.xml, excluding nested ones."""
    roots = []
    for root, _dirs, files in os.walk(install_dir):
        if "addon.xml" not in files:
            continue
        if any(root.startswith(r + os.sep) for r in roots):
            continue
        roots.append(root)
    return roots


def updaterepoaddon(repodir, builddir, addonname, kodirev, kodihash, addonrev, addonhash):
    """Package the build output into repodir and regenerate addons.xml(.md5).

    Returns the number of addon packages created.
    """
    install_dir = os.path.join(builddir, addonname, ".install")
    new_version = f"{kodirev}.{addonrev}.{kodihash}.{addonhash}"
    os.makedirs(repodir, exist_ok=True)

    for root, _dirs, files in os.walk(install_dir):
        for file in files:
            if file.endswith(".so"):
                run_cmd("strip", "--strip-unneeded", os.path.join(root, file),
                        exitonerror=False)

    # 2. Update version and package each addon.
    packaged = 0
    for root in find_addon_roots(install_dir):
        xml_path = os.path.join(root, "addon.xml")
        tree = ET.parse(xml_path)
        xml_root = tree.getroot()
        addon_id = xml_root.attrib.get("id", addonname)
        xml_root.set("version", new_version)
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)

        zip_basename = f"{addon_id}-{new_version}"
        zip_output_dir = os.path.join(builddir, addonname)
        archive_path = shutil.make_archive(
            os.path.join(zip_output_dir, zip_basename),
            "zip",
            root_dir=os.path.dirname(root),
            base_dir=os.path.basename(root),
        )
        shutil.copy(archive_path, os.path.join(repodir, os.path.basename(archive_path)))
        packaged += 1

    if not packaged:
        logger.error("No addon.xml found in %s, nothing packaged", install_dir)
        return 0

    # 3. Rescan the repo, prune old versions, regenerate addons.xml.
    addon_zips = {}
    for filename in os.listdir(repodir):
        if not filename.endswith(".zip"):
            continue

        zip_path = os.path.join(repodir, filename)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                xml_in_zip = next((n for n in zf.namelist() if n.endswith("addon.xml")), None)
                if not xml_in_zip:
                    continue

                with zf.open(xml_in_zip) as xf:
                    xml_root = ET.parse(xf).getroot()
                    a_id = xml_root.attrib.get("id")
                    version_str = xml_root.attrib.get("version")

                    if not a_id or not version_str:
                        continue

                    addon_zips.setdefault(a_id, []).append(
                        (parseaddonversion(version_str), filename, xml_root)
                    )
        except Exception as e:
            logger.warning("Failed to inspect addon.xml in %s: %s", filename, e)

    addons_root = ET.Element("addons")

    for a_id, entries in addon_zips.items():
        entries.sort(key=lambda x: x[0], reverse=True)

        to_keep = entries[:ADDONHISTORY]
        to_delete = entries[ADDONHISTORY:]

        for _, fname, _ in to_delete:
            try:
                os.remove(os.path.join(repodir, fname))
                logger.info("Removed old package version: %s", fname)
            except OSError as e:
                logger.warning("Failed to remove old package %s: %s", fname, e)

        for _, _, xml_root in to_keep:
            addons_root.append(xml_root)

    addons_xml_path = os.path.join(repodir, "addons.xml")
    addons_md5_path = os.path.join(repodir, "addons.xml.md5")

    if hasattr(ET, "indent"):
        ET.indent(addons_root, space="  ")

    xml_bytes = ET.tostring(addons_root, encoding="utf-8", xml_declaration=True)
    with open(addons_xml_path, "wb") as f:
        f.write(xml_bytes)

    with open(addons_md5_path, "w", encoding="utf-8") as f:
        f.write(hashlib.md5(xml_bytes).hexdigest())

    return packaged


def buildaddon(srcdir, builddir, repodir, kodirev, kodihash, addon, env):
    addonenv = env.copy()
    addonenv.update(addon.get("env", {}))
    addonname = addon["name"]
    addonhash, addonrev = checkout(srcdir, addonname, addon["url"], addon["ref"], addon.get("commit"))
    newver = (kodirev, addonrev, kodihash, addonhash)

    existing = existingversions(repodir, addonname)
    if newver in existing:
        logger.info("%s has no update, skipping", addonname)
        return SKIPPED, addonrev, addonhash

    logger.info("%s addon is being built: %s -> %s",
                addonname, max(existing) if existing else None, newver)
    addon_builddir = os.path.join(builddir, addonname)
    shutil.rmtree(addon_builddir, ignore_errors=True)
    os.makedirs(addon_builddir, exist_ok=True)
    cmake_cmd = [
        "cmake",
        f"-DADDONS_TO_BUILD={addonname}",
        f"-DADDON_SRC_PREFIX={srcdir}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DAPP_RENDER_SYSTEM=gles",
        f"-DCMAKE_INSTALL_PREFIX={addon_builddir}/.install",
        "-DPACKAGE_ZIP=ON",
        "-Wno-dev",
        f"{srcdir}/kodi/cmake/addons",
    ]

    make_cmd = ["make", f"-j{multiprocessing.cpu_count()}"]
    for cmd in (cmake_cmd, make_cmd):
        err, _ = run_cmd(*cmd, cwd=addon_builddir, env=addonenv, exitonerror=False)
        if err:
            logger.error("Failed to build addon %s", addonname)
            return FAILED, addonrev, addonhash

    logger.info("Successfully built addon %s", addonname)
    return BUILT, addonrev, addonhash


def buildaddons(config, srcdir, builddir, repodir, env):
    kodihash, kodirev = checkout(srcdir, KODI, config[KODI]["url"], config[KODI]["ref"],
                                 config[KODI].get("commit"))
    kodienv = env.copy()
    kodienv.update(config[KODI].get("env", {}))
    failures = []
    for addon in config[ADDONS]:
        name = addon["name"]
        state, addonrev, addonhash = buildaddon(
            srcdir, builddir, repodir, kodirev, kodihash, addon, kodienv)
        if state == SKIPPED:
            continue
        if state == FAILED:
            failures.append(name)
            continue
        if not updaterepoaddon(repodir, builddir, name, kodirev, kodihash,
                               addonrev, addonhash):
            failures.append(name)
    return failures


def main(argv):
    if len(argv) != 2:
        print(f"Usage: {argv[0]} <config.json>", file=sys.stderr)
        return 2

    config = loadconfig(argv[1])

    basedir = config["name"]
    srcdir = os.path.abspath(os.path.join(basedir, "src"))
    builddir = os.path.abspath(os.path.join(basedir, "build"))
    repodir = os.path.abspath(os.path.join(basedir, "repo"))
    for d in (srcdir, builddir, repodir):
        os.makedirs(d, exist_ok=True)

    failures = buildaddons(config, srcdir, builddir, repodir, os.environ)
    if failures:
        logger.error("Failed addons: %s", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
