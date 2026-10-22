package com.example.model

enum class SortOption(val label: String, val iconName: String) {
    FAVORITED_NEWEST("Latest Favorited", "favorite"),
    FAVORITED_OLDEST("Oldest Favorited", "favorite_border"),
    DATE_NEWEST("Newest Added", "history"),
    FIRST_SEEN_NEWEST("Recently Detected (First Seen)", "visibility"),
    DATE_PINTEREST_CREATED("Pinterest Created Date", "event"),
    DATE_OLDEST("Oldest Added", "schedule"),
    ASPECT_TALL("Tall Pins First", "crop_portrait"),
    ASPECT_WIDE("Wide Pins First", "crop_landscape"),
    TITLE_AZ("Title: A to Z", "sort_by_alpha"),
    TITLE_ZA("Title: Z to A", "sort_by_alpha"),
    MOST_SAVED("Most Saved", "bookmark"),
    FEWEST_SAVED("Fewest Saved", "bookmark_border"),
    MOST_LIKED("Most Liked", "favorite"),
    FEWEST_LIKED("Fewest Liked", "favorite_border"),
    RESOLUTION_HIGH("High Resolution", "hd"),
    RESOLUTION_LOW("Small Resolution", "photo_size_select_small"),
    FILE_SIZE_LARGE("Largest Size", "data_usage"),
    FILE_SIZE_SMALL("Smallest Size", "file_download"),
    AUTHOR_AZ("Author: A to Z", "person"),
    SHUFFLE_RANDOM("Shuffle / Random", "shuffle")
}
