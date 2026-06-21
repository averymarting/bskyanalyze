#!/usr/bin/env python3
"""
Bluesky Account Performance Analyzer
-------------------------------------
Logs into Bluesky (bsky.app) via AT Protocol using a handle + app password,
pulls your post history, optionally filters posts by a keyword/phrase, and
ranks them by engagement (likes, reposts, replies) so you can see what
content performs best.

Auth (set as environment variables / GitHub Actions secrets):
    BSKY_HANDLE        e.g. yourname.bsky.social
    BSKY_APP_PASSWORD  an App Password generated in Bluesky settings
                        (NOT your main account password)

Optional inputs:
    SEARCH_TERM   only include posts whose text contains this (case-insensitive)
    TOP_N         how many top posts to show (default 10)
    MAX_POSTS     max number of recent posts to scan (default 500)

Usage:
    python scripts/bluesky_top_posts.py
    SEARCH_TERM="launch" TOP_N=5 python scripts/bluesky_top_posts.py
"""

import os
import sys
from datetime import datetime, timezone

try:
    from atproto import Client
except ImportError:
    print("Missing dependency. Install with: pip install atproto", file=sys.stderr)
    sys.exit(1)


def get_env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        print(f"ERROR: required environment variable '{name}' is not set.", file=sys.stderr)
        sys.exit(1)
    return val


def fetch_all_posts(client, actor, max_posts):
    """Fetch the author's own posts (skips reposts of other people's content)."""
    posts = []
    cursor = None

    while len(posts) < max_posts:
        resp = client.get_author_feed(actor=actor, cursor=cursor, limit=100)
        if not resp.feed:
            break

        for item in resp.feed:
            # Skip items that are reposts of someone else's content
            if getattr(item, "reason", None) is not None:
                continue

            post = item.post
            record = post.record
            text = getattr(record, "text", "") or ""

            posts.append({
                "uri": post.uri,
                "cid": post.cid,
                "text": text,
                "likes": post.like_count or 0,
                "reposts": post.repost_count or 0,
                "replies": post.reply_count or 0,
                "quotes": getattr(post, "quote_count", 0) or 0,
                "created_at": getattr(record, "created_at", None),
                "url": uri_to_url(post.uri, actor),
            })

        cursor = resp.cursor
        if not cursor:
            break

    return posts[:max_posts]


def uri_to_url(uri, handle):
    """Convert an at:// post URI into a clickable bsky.app URL."""
    try:
        rkey = uri.split("/")[-1]
        return f"https://bsky.app/profile/{handle}/post/{rkey}"
    except Exception:
        return uri


def engagement_score(p):
    # Weighted score: likes count most, then reposts/quotes (amplification), then replies
    return p["likes"] + (p["reposts"] * 2) + (p["quotes"] * 2) + p["replies"]


def main():
    handle = get_env("BSKY_HANDLE", required=True)
    app_password = get_env("BSKY_APP_PASSWORD", required=True)
    search_term = get_env("SEARCH_TERM", default="").strip()
    top_n = int(get_env("TOP_N", default="10"))
    max_posts = int(get_env("MAX_POSTS", default="500"))

    print(f"Logging in as {handle} ...")
    client = Client()
    try:
        client.login(handle, app_password)
    except Exception as e:
        print(f"Login failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching up to {max_posts} recent posts ...")
    posts = fetch_all_posts(client, handle, max_posts)
    print(f"Fetched {len(posts)} original posts.")

    if search_term:
        filtered = [p for p in posts if search_term.lower() in p["text"].lower()]
        print(f"Filtered to {len(filtered)} posts containing: \"{search_term}\"")
    else:
        filtered = posts

    if not filtered:
        print("No posts matched. Try a different SEARCH_TERM or check the handle.")
        return

    # --- Overall account summary ---
    total_likes = sum(p["likes"] for p in filtered)
    total_reposts = sum(p["reposts"] for p in filtered)
    total_replies = sum(p["replies"] for p in filtered)
    total_quotes = sum(p["quotes"] for p in filtered)
    count = len(filtered)

    print("\n" + "=" * 60)
    print("OVERALL PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"Posts analyzed:      {count}")
    print(f"Total likes:         {total_likes}")
    print(f"Total reposts:       {total_reposts}")
    print(f"Total quotes:        {total_quotes}")
    print(f"Total replies:       {total_replies}")
    print(f"Avg likes/post:      {total_likes / count:.1f}")
    print(f"Avg reposts/post:    {total_reposts / count:.1f}")
    print(f"Avg replies/post:    {total_replies / count:.1f}")

    # --- Ranked by likes ---
    by_likes = sorted(filtered, key=lambda p: p["likes"], reverse=True)[:top_n]
    print("\n" + "=" * 60)
    print(f"TOP {len(by_likes)} POSTS BY LIKES")
    print("=" * 60)
    for i, p in enumerate(by_likes, 1):
        print_post(i, p)

    # --- Ranked by overall engagement (likes + reposts*2 + quotes*2 + replies) ---
    by_engagement = sorted(filtered, key=engagement_score, reverse=True)[:top_n]
    print("\n" + "=" * 60)
    print(f"TOP {len(by_engagement)} POSTS BY OVERALL ENGAGEMENT")
    print("(likes + reposts*2 + quotes*2 + replies)")
    print("=" * 60)
    for i, p in enumerate(by_engagement, 1):
        print_post(i, p, show_score=True)

    print("\nDone.")


def print_post(i, p, show_score=False):
    snippet = p["text"].replace("\n", " ").strip()
    if len(snippet) > 100:
        snippet = snippet[:97] + "..."
    score_str = f" | score: {engagement_score(p)}" if show_score else ""
    print(f"\n{i}. {snippet}")
    print(f"   likes: {p['likes']} | reposts: {p['reposts']} | quotes: {p['quotes']} | replies: {p['replies']}{score_str}")
    if p["created_at"]:
        print(f"   posted: {p['created_at']}")
    print(f"   url: {p['url']}")


if __name__ == "__main__":
    main()
