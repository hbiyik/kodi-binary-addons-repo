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

import argparse
import hashlib
import logging
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(funcName)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def parse_dir_spec(spec):
    """Parse `<root_url>[:<min_version>[:<max_version>]]` into a dict.

    Examples:
      - https://.../Omega-gl-amd64
      - https://.../Omega-gl-amd64:21.0.0
      - https://.../Omega-gl-amd64:21.0.0:21.9.9
      - https://.../Piers-gl-amd64::22.9.9
    """
    scheme_idx = spec.find("://")
    search_start = scheme_idx + 3 if scheme_idx != -1 else 0
    first_colon = spec.find(":", search_start)

    if first_colon == -1:
        return {
            "root_url": spec.rstrip("/"),
            "min_version": None,
            "max_version": None,
        }

    root_url = spec[:first_colon].rstrip("/")
    rest = spec[first_colon + 1 :]
    if ":" in rest:
        min_ver, max_ver = rest.split(":", 1)
    else:
        min_ver, max_ver = rest, None

    return {
        "root_url": root_url,
        "min_version": min_ver.strip() if min_ver and min_ver.strip() else None,
        "max_version": max_ver.strip() if max_ver and max_ver.strip() else None,
    }


def rewrite_addons_xml_datadir(repodir, root_url):
    """Update <datadir> URLs in addons.xml and regenerate addons.xml.md5 if present."""
    addons_xml_path = os.path.join(repodir, "addons.xml")
    if not os.path.isfile(addons_xml_path):
        return

    tree = ET.parse(addons_xml_path)
    root = tree.getroot()
    changed = False

    datadir_text = f"{root_url}/"
    for addon_el in root.findall("addon"):
        for ext_el in addon_el.findall("extension"):
            for dir_el in ext_el.findall("dir"):
                datadir_el = dir_el.find("datadir")
                if datadir_el is not None and datadir_el.text != datadir_text:
                    datadir_el.text = datadir_text
                    changed = True
            datadir_el = ext_el.find("datadir")
            if datadir_el is not None and datadir_el.text != datadir_text:
                datadir_el.text = datadir_text
                changed = True

    if not changed:
        return

    if hasattr(ET, "indent"):
        ET.indent(root, space="  ")

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with open(addons_xml_path, "wb") as fp:
        fp.write(xml_bytes)

    addons_md5_path = os.path.join(repodir, "addons.xml.md5")
    with open(addons_md5_path, "w", encoding="utf-8") as fp:
        fp.write(hashlib.md5(xml_bytes).hexdigest())

    logger.info("Updated <datadir> in %s -> %s", addons_xml_path, datadir_text)


def generate_repo_addon(
    repodir,
    repo_id,
    repo_name,
    repo_version,
    dir_specs,
):
    """Generate <repo_id>-<version>.zip inside repodir with one <dir> per root spec."""
    if not dir_specs:
        raise ValueError("At least one --root specification is required.")

    os.makedirs(repodir, exist_ok=True)
    if len(dir_specs) == 1:
        rewrite_addons_xml_datadir(repodir, dir_specs[0]["root_url"])

    with tempfile.TemporaryDirectory() as tmpdir:
        addon_dir = os.path.join(tmpdir, repo_id)
        os.makedirs(addon_dir, exist_ok=True)

        addon_el = ET.Element(
            "addon",
            **{
                "id": repo_id,
                "name": repo_name,
                "version": repo_version,
                "provider-name": repo_name,
            },
        )
        repo_ext = ET.SubElement(
            addon_el,
            "extension",
            point="xbmc.addon.repository",
            name=repo_name,
        )

        for spec in dir_specs:
            dir_attribs = {}
            if spec.get("min_version"):
                dir_attribs["minversion"] = spec["min_version"]
            if spec.get("max_version"):
                dir_attribs["maxversion"] = spec["max_version"]

            dir_el = ET.SubElement(repo_ext, "dir", **dir_attribs)
            clean_root = spec["root_url"].rstrip("/")

            info_el = ET.SubElement(dir_el, "info", compressed="false")
            info_el.text = f"{clean_root}/addons.xml"

            checksum_el = ET.SubElement(dir_el, "checksum")
            checksum_el.text = f"{clean_root}/addons.xml.md5"

            datadir_el = ET.SubElement(dir_el, "datadir", zip="true")
            datadir_el.text = f"{clean_root}/"

        meta_ext = ET.SubElement(addon_el, "extension", point="xbmc.addon.metadata")
        summary_el = ET.SubElement(meta_ext, "summary", lang="en_GB")
        summary_el.text = repo_name
        platform_el = ET.SubElement(meta_ext, "platform")
        platform_el.text = "all"

        if hasattr(ET, "indent"):
            ET.indent(addon_el, space="  ")

        xml_bytes = ET.tostring(addon_el, encoding="utf-8", xml_declaration=True)
        with open(os.path.join(addon_dir, "addon.xml"), "wb") as fp:
            fp.write(xml_bytes)

        zip_basename = f"{repo_id}-{repo_version}"
        archive_path = shutil.make_archive(
            os.path.join(tmpdir, zip_basename),
            "zip",
            root_dir=tmpdir,
            base_dir=repo_id,
        )
        dest_zip = os.path.join(repodir, os.path.basename(archive_path))
        shutil.copy2(archive_path, dest_zip)

    logger.info("Generated %s with %d <dir> entries", dest_zip, len(dir_specs))
    return dest_zip


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Generate Kodi repository add-on zip and update repo metadata URLs."
    )
    parser.add_argument(
        "repodir",
        help="Output directory for the generated repository zip (and addons.xml if single --root)",
    )
    parser.add_argument(
        "--id",
        required=True,
        dest="repo_id",
        help="Repository add-on ID (e.g. repository.binaryaddons)",
    )
    parser.add_argument(
        "--name",
        required=True,
        dest="repo_name",
        help="Repository add-on display name",
    )
    parser.add_argument(
        "--version",
        default="0.0.1",
        dest="repo_version",
        help="Repository add-on version (default: 0.0.1)",
    )
    parser.add_argument(
        "--root",
        required=True,
        action="append",
        dest="roots",
        help=(
            "Root spec as <url>[:<min_version>[:<max_version>]]. "
            "Repeat --root for each Kodi version <dir>."
        ),
    )
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    dir_specs = [parse_dir_spec(r) for r in args.roots]
    generate_repo_addon(
        repodir=os.path.abspath(args.repodir),
        repo_id=args.repo_id,
        repo_name=args.repo_name,
        repo_version=args.repo_version,
        dir_specs=dir_specs,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
