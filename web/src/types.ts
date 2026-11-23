export interface AuthStatus {
  authenticated: boolean;
  mode: "demo" | "zhihu" | "extension" | null;
  user_id: string | null;
  oauth_configured: boolean;
  demo_enabled: boolean;
  oauth_expires_at: number | null;
  oauth_expired: boolean;
}

export interface Paging {
  IsEnd: boolean;
  NextOffset?: string | null;
  Totals?: number;
}

export interface Profile {
  uid: string;
  hash_id: string;
  fullname: string;
  headline: string;
  description: string;
  avatar_path: string;
  url: string;
}

export interface Author {
  Name?: string;
  Url?: string;
  Headline?: string;
}

export interface ContentItem {
  ContentType: string;
  Url: string;
  Title: string;
  Summary: string;
  Author?: Author;
  LikeCount?: number;
  CommentCount?: number;
  FavoriteCount?: number;
  CreatedAt?: number;
  FavTime?: number;
}

export interface Favlist {
  UrlToken: number;
  Url: string;
  Title: string;
  Description: string;
  IsPublic: boolean;
}

export interface Followee {
  Fullname: string;
  Url: string;
  AvatarUrl: string;
  Headline: string;
  FollowerCount: number;
}

export interface ArticleGroup {
  article_key: string;
  source_url: string;
  content_type: string;
  content_id: string;
  title: string;
  author_name: string;
  bubble_count: number;
  last_bubble_at: number;
}

export interface Bubble {
  id: string;
  article_key: string;
  source_url: string;
  title: string;
  author_name: string;
  body: string;
  quote: string;
  created_at: number;
}
