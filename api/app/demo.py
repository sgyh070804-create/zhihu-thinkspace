from __future__ import annotations


PROFILE = {
    "uid": "0",
    "hash_id": "thinkspace-demo",
    "fullname": "演示用户",
    "headline": "本地演示身份，不是真实知乎账号",
    "description": "",
    "avatar_path": "",
    "url": "",
}

AUTHOR = {
    "Name": "演示作者",
    "UrlToken": "thinkspace-demo",
    "Url": "https://www.zhihu.com/people/thinkspace-demo",
    "Gender": 0,
    "Headline": "本地虚构数据，不是真实知乎用户",
}

ARTICLES = [
    {
        "ContentType": "answer",
        "Url": "https://www.zhihu.com/question/10001/answer/20001",
        "CreatedAt": 1770000000,
        "FavTime": 1770000100,
        "LikeCount": 12,
        "CommentCount": 3,
        "FavoriteCount": 5,
        "Title": "演示：为什么阅读时需要记录疑问？",
        "Summary": "这是本地演示摘要，用来验证收藏与文章的展示，不代表真实知乎内容。",
        "Favlists": [
            {
                "UrlToken": 90001,
                "Title": "演示收藏夹",
                "Url": "https://www.zhihu.com/collection/90001",
            }
        ],
        "Author": AUTHOR,
    },
    {
        "ContentType": "article",
        "Url": "https://zhuanlan.zhihu.com/p/30001",
        "CreatedAt": 1770000200,
        "FavTime": 1770000300,
        "LikeCount": 8,
        "CommentCount": 2,
        "FavoriteCount": 4,
        "Title": "演示：从收藏走向自己的判断",
        "Summary": "收藏只代表保存，不等于赞同；想法需要由用户主动确认。",
        "Favlists": [],
        "Author": AUTHOR,
    },
]

FAVLISTS = {
    "Items": [
        {
            "UrlToken": 90001,
            "Url": "https://www.zhihu.com/collection/90001",
            "Title": "演示收藏夹",
            "Description": "仅用于离线产品验证",
            "IsPublic": True,
        }
    ]
}

def _creation(index: int) -> dict:
    n = index + 1
    kind = ("answer", "article", "pin", "zvideo")[index % 4]
    urls = {
        "answer": f"https://www.zhihu.com/question/1000{n}/answer/2000{n}",
        "article": f"https://zhuanlan.zhihu.com/p/3000{n}",
        "pin": f"https://www.zhihu.com/pin/4000{n}",
        "zvideo": f"https://www.zhihu.com/zvideo/5000{n}",
    }
    return {
        "ContentType": kind,
        "Url": urls[kind],
        "CreatedAt": 1770000000 + index * 86400,
        "LikeCount": (index * 7) % 23,
        "CommentCount": (index * 3) % 9,
        "FavoriteCount": (index * 5) % 17,
        "Title": f"演示创作 {n}：思考练习之{kind}",
        "Summary": "本地演示摘要：这条内容用于验证创作列表分页与加载更多，不代表真实知乎内容。",
        "Author": AUTHOR,
    }


CREATIONS = [_creation(i) for i in range(12)]


def _followee(index: int) -> dict:
    return {
        "Fullname": f"演示关注对象 {index + 1}",
        "UrlToken": f"thinkspace-demo-friend-{index + 1}",
        "Url": f"https://www.zhihu.com/people/thinkspace-demo-friend-{index + 1}",
        "AvatarUrl": "",
        "Headline": "本地虚构数据，不是真实知乎用户",
        "Gender": index % 2 + 1,
        "FollowerCount": (index * 137) % 900,
    }


FOLLOWEE_POOL = [_followee(i) for i in range(8)]


def followees_page(offset: int, limit: int) -> dict:
    return page(FOLLOWEE_POOL, offset, limit)



def page(items: list[dict], offset: int, limit: int) -> dict:
    selected = items[offset : offset + limit]
    next_offset = offset + limit
    return {
        "Items": selected,
        "Paging": {
            "IsEnd": next_offset >= len(items),
            "NextOffset": str(next_offset) if next_offset < len(items) else None,
            "Totals": len(items),
        },
    }
