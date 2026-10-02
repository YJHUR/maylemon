#!/usr/bin/env python3
"""Export the restored maylemon WordPress database into Jekyll content."""

from __future__ import annotations

import argparse
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

import pymysql
import yaml
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPLOADS = ROOT / ".migration/wordpress/wp-content/uploads"
GUTENBERG_COMMENT = re.compile(r"<!--\s*/?wp:[\s\S]*?-->")
SERIALIZED_ID = re.compile(r's:\d+:"(\d+)";')


def connect() -> pymysql.Connection:
    return pymysql.connect(
        host=os.environ.get("MAYLEMON_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("MAYLEMON_DB_PORT", "3307")),
        user=os.environ.get("MAYLEMON_DB_USER", "root"),
        password=os.environ.get("MAYLEMON_DB_PASSWORD", ""),
        database=os.environ.get("MAYLEMON_DB_NAME", "maylemon"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def fetch_all(connection: pymysql.Connection, sql: str) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return list(cursor.fetchall())


def clean_content(content: str, uploads: Path = DEFAULT_UPLOADS) -> str:
    content = GUTENBERG_COMMENT.sub("", content or "")
    content = re.sub(r"https?://(?:www\.)?maylemon\.net", "", content)
    soup = BeautifulSoup(content, "html.parser")
    by_filename: dict[str, list[Path]] = defaultdict(list)
    for item in uploads.rglob("*"):
        if item.is_file():
            by_filename[item.name].append(item)

    for node in soup.select("[src], [href]"):
        for attribute in ("src", "href"):
            url = node.get(attribute, "")
            prefix = "/wp-content/uploads/"
            if not url.startswith(prefix):
                continue
            relative = Path(unquote(url.removeprefix(prefix)))
            if (uploads / relative).exists():
                continue
            matches = by_filename.get(relative.name, [])
            if len(matches) == 1:
                node[attribute] = prefix + matches[0].relative_to(uploads).as_posix()
            elif attribute == "href":
                image = node.find("img", src=True)
                if image and image["src"].startswith(prefix):
                    node[attribute] = image["src"]
    return str(soup).strip()


def write_front_matter(path: Path, data: dict, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    front_matter = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    path.write_text(f"---\n{front_matter}\n---\n\n{content}\n", encoding="utf-8")


def export_posts(connection: pymysql.Connection) -> int:
    posts = fetch_all(
        connection,
        """
        SELECT p.ID, p.post_author, p.post_date, p.post_modified, p.post_title,
               p.post_name, p.post_content, p.post_excerpt, u.display_name
        FROM wp_posts p
        LEFT JOIN wp_users u ON u.ID = p.post_author
        WHERE p.post_type = 'post' AND p.post_status = 'publish'
        ORDER BY p.post_date
        """,
    )
    terms = fetch_all(
        connection,
        """
        SELECT tr.object_id, tt.taxonomy, t.name, t.slug
        FROM wp_term_relationships tr
        JOIN wp_term_taxonomy tt ON tt.term_taxonomy_id = tr.term_taxonomy_id
        JOIN wp_terms t ON t.term_id = tt.term_id
        WHERE tt.taxonomy IN ('category', 'post_tag', 'post_format')
        ORDER BY tr.term_order, t.name
        """,
    )
    metas = fetch_all(
        connection,
        """
        SELECT post_id, meta_key, meta_value
        FROM wp_postmeta
        WHERE meta_key IN (
          '_thumbnail_id', '_zilla_likes', 'gallery_of_images',
          '_yoast_wpseo_metadesc', '_yoast_wpseo_title'
        )
        """,
    )
    attachments = fetch_all(
        connection,
        """
        SELECT p.ID, p.post_title, p.post_excerpt AS caption,
               file.meta_value AS attached_file,
               alt.meta_value AS alt_text
        FROM wp_posts p
        JOIN wp_postmeta file
          ON file.post_id = p.ID AND file.meta_key = '_wp_attached_file'
        LEFT JOIN wp_postmeta alt
          ON alt.post_id = p.ID AND alt.meta_key = '_wp_attachment_image_alt'
        WHERE p.post_type = 'attachment'
        """,
    )

    terms_by_post: dict[int, dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for term in terms:
        terms_by_post[term["object_id"]][term["taxonomy"]].append(term)

    meta_by_post: dict[int, dict[str, str]] = defaultdict(dict)
    for meta in metas:
        meta_by_post[meta["post_id"]][meta["meta_key"]] = meta["meta_value"]

    attachment_by_id = {item["ID"]: item for item in attachments}
    output = ROOT / "_posts"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()

    for post in posts:
        post_id = post["ID"]
        meta = meta_by_post[post_id]
        taxonomy = terms_by_post[post_id]
        thumbnail_id = int(meta.get("_thumbnail_id") or 0)
        thumbnail = attachment_by_id.get(thumbnail_id)
        gallery_ids = [int(value) for value in SERIALIZED_ID.findall(
            meta.get("gallery_of_images", "")
        )]
        gallery = [
            {
                "src": f"/wp-content/uploads/{attachment_by_id[item]['attached_file']}",
                "alt": attachment_by_id[item]["alt_text"] or "",
            }
            for item in gallery_ids
            if item in attachment_by_id
        ]
        decoded_slug = unquote(post["post_name"])
        data = {
            "layout": "post",
            "title": post["post_title"],
            "date": post["post_date"].strftime("%Y-%m-%d %H:%M:%S +0900"),
            "modified": post["post_modified"].strftime("%Y-%m-%d %H:%M:%S +0900"),
            "author": post["display_name"] or "Lemon",
            "wordpress_id": post_id,
            "permalink": f"/{decoded_slug}/",
            "categories": [item["name"] for item in taxonomy["category"]],
            "category_slugs": [item["slug"] for item in taxonomy["category"]],
            "tags": [item["name"] for item in taxonomy["post_tag"]],
            "tag_slugs": [item["slug"] for item in taxonomy["post_tag"]],
            "likes": int(meta.get("_zilla_likes") or 0),
        }
        if thumbnail:
            data["featured_image"] = (
                f"/wp-content/uploads/{thumbnail['attached_file']}"
            )
            data["featured_image_alt"] = thumbnail["alt_text"] or post["post_title"]
        if gallery:
            data["gallery"] = gallery
        if taxonomy["post_format"]:
            data["post_format"] = taxonomy["post_format"][0]["slug"].removeprefix(
                "post-format-"
            )
        if meta.get("_yoast_wpseo_title"):
            data["seo_title"] = meta["_yoast_wpseo_title"]
        if meta.get("_yoast_wpseo_metadesc"):
            data["description"] = meta["_yoast_wpseo_metadesc"]

        filename = f"{post['post_date']:%Y-%m-%d}-{post_id}.html"
        write_front_matter(
            output / filename,
            data,
            clean_content(post["post_content"]),
        )
    return len(posts)


def copy_media(source: Path) -> int:
    destination = ROOT / "wp-content/uploads"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return sum(1 for item in destination.rglob("*") if item.is_file())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--copy-media",
        action="store_true",
        help="Copy the backed-up WordPress uploads into the Jekyll site.",
    )
    parser.add_argument("--uploads", type=Path, default=DEFAULT_UPLOADS)
    args = parser.parse_args()

    with connect() as connection:
        post_count = export_posts(connection)
    print(f"Exported {post_count} published posts.")

    if args.copy_media:
        file_count = copy_media(args.uploads)
        print(f"Copied {file_count} upload files.")


if __name__ == "__main__":
    main()
