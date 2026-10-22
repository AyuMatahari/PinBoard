package com.example

import com.example.data.PinterestRepository
import com.example.model.PinItem
import com.example.model.PinterestBoard
import com.example.model.SortOption
import com.example.util.Downloader
import com.example.viewmodel.PinBoardViewModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PinBoardGalleryTest {

    private val repository = PinterestRepository()

    private fun createTestBoard(): PinterestBoard {
        val pins = listOf(
            PinItem(
                id = "pin1",
                title = "Beta Design",
                description = "Modern design",
                imageUrl = "https://i.pinimg.com/736x/test1.jpg",
                thumbnailUrl = "https://i.pinimg.com/236x/test1.jpg",
                author = "creator",
                boardName = "Test Board",
                sourceUrl = "https://pinterest.com/test",
                width = 736,
                height = 1000,
                dateAddedMillis = 1000L,
                savesCount = 500,
                likesCount = 200,
                fileSizeKb = 300
            ),
            PinItem(
                id = "pin2",
                title = "Alpha Architecture",
                description = "Cool building",
                imageUrl = "https://i.pinimg.com/736x/test2.jpg",
                thumbnailUrl = "https://i.pinimg.com/236x/test2.jpg",
                author = "creator",
                boardName = "Test Board",
                sourceUrl = "https://pinterest.com/test",
                width = 736,
                height = 800,
                dateAddedMillis = 2000L,
                savesCount = 1200,
                likesCount = 600,
                fileSizeKb = 450
            )
        )
        return PinterestBoard(
            id = "test-board",
            title = "Test Board",
            slug = "test-board",
            ownerUsername = "testuser",
            ownerDisplayName = "Test User",
            ownerAvatarUrl = "https://ui-avatars.com/api/?name=testuser",
            pinCount = pins.size,
            followerCount = 100,
            boardUrl = "https://www.pinterest.com/testuser/test-board/",
            description = "A test board",
            pins = pins
        )
    }

    @Test
    fun `test Pinterest folder name is PinterestViewerDownloads`() {
        assertEquals("PinterestViewerDownloads", Downloader.FOLDER_NAME)
    }

    @Test
    fun `test parse Pinterest URL with standard board link`() {
        val parsed = repository.parsePinterestUrl("https://www.pinterest.com/minimal_spaces/architectural-digest/")
        assertNotNull(parsed)
        assertEquals("minimal_spaces", parsed?.first)
        assertEquals("architectural-digest", parsed?.second)
    }

    @Test
    fun `test parse Pinterest URL without trailing slash`() {
        val parsed = repository.parsePinterestUrl("https://pinterest.com/nordic_cafe/cozy-coffee-bakery")
        assertNotNull(parsed)
        assertEquals("nordic_cafe", parsed?.first)
        assertEquals("cozy-coffee-bakery", parsed?.second)
    }

    @Test
    fun `test board is empty by default with zero stock photos`() {
        val viewModel = PinBoardViewModel(repository)
        assertNull("Current board should be null initially", viewModel.currentBoard.value)
        assertTrue("Displayed pins should be empty by default", viewModel.displayedPins.value.isEmpty())
    }

    @Test
    fun `test board history is updated and can be cleared`() {
        val viewModel = PinBoardViewModel(repository)
        val board = createTestBoard()
        viewModel.selectBoard(board)

        val history = viewModel.boardHistory.value
        // Board history contains the selected Pinterest board at index 0, followed by special boards
        assertTrue(history.isNotEmpty())
        assertEquals(board.boardUrl, history[0].url)
        assertEquals(board.title, history[0].title)

        viewModel.removeHistoryItem(board.boardUrl)
        assertFalse(viewModel.boardHistory.value.any { it.url == board.boardUrl })

        viewModel.selectBoard(board)
        assertEquals(board.boardUrl, viewModel.boardHistory.value[0].url)
        viewModel.clearHistory()
        assertFalse(viewModel.boardHistory.value.any { it.url == board.boardUrl })
    }

    @Test
    fun `test selecting existing board in history preserves its order and position`() {
        val viewModel = PinBoardViewModel(repository)
        val board1 = createTestBoard().copy(boardUrl = "https://pinterest.com/user/board1", title = "Board 1")
        val board2 = createTestBoard().copy(boardUrl = "https://pinterest.com/user/board2", title = "Board 2")
        val board3 = createTestBoard().copy(boardUrl = "https://pinterest.com/user/board3", title = "Board 3")

        viewModel.selectBoard(board1)
        viewModel.selectBoard(board2)
        viewModel.selectBoard(board3)

        val historyBefore = viewModel.boardHistory.value
        assertEquals("Board 1", historyBefore[0].title)
        assertEquals("Board 2", historyBefore[1].title)
        assertEquals("Board 3", historyBefore[2].title)

        // Select board2 again - it should NOT move to index 0, it must remain at index 1!
        viewModel.selectBoard(board2)
        val historyAfter = viewModel.boardHistory.value
        assertEquals("Board 1", historyAfter[0].title)
        assertEquals("Board 2", historyAfter[1].title)
        assertEquals("Board 3", historyAfter[2].title)
    }

    @Test
    fun `test column switching between 2, 3, and 4`() {
        val viewModel = PinBoardViewModel(repository)
        assertEquals(2, viewModel.columnCount.value)

        viewModel.setColumnCount(3)
        assertEquals(3, viewModel.columnCount.value)

        viewModel.setColumnCount(4)
        assertEquals(4, viewModel.columnCount.value)

        // Invalid counts should be ignored
        viewModel.setColumnCount(5)
        assertEquals(4, viewModel.columnCount.value)
    }

    @Test
    fun `test multi-select and select all functionality`() {
        val viewModel = PinBoardViewModel(repository)
        viewModel.selectBoard(createTestBoard())
        val initialPins = viewModel.displayedPins.value
        assertEquals(2, initialPins.size)

        viewModel.enterSelectionMode(initialPins[0].id)
        assertTrue(viewModel.isSelectionMode.value)
        assertEquals(1, viewModel.selectedPinIds.value.size)

        viewModel.toggleSelection(initialPins[1].id)
        assertEquals(2, viewModel.selectedPinIds.value.size)

        viewModel.selectAll()
        assertEquals(initialPins.size, viewModel.selectedPinIds.value.size)

        viewModel.clearSelection()
        assertFalse(viewModel.isSelectionMode.value)
        assertEquals(0, viewModel.selectedPinIds.value.size)
    }

    @Test
    fun `test sorting options work as expected`() {
        val viewModel = PinBoardViewModel(repository)
        viewModel.selectBoard(createTestBoard())

        viewModel.setSortOption(SortOption.TITLE_AZ)
        assertEquals(SortOption.TITLE_AZ, viewModel.sortOption.value)

        val sortedAz = viewModel.displayedPins.value
        for (i in 0 until sortedAz.size - 1) {
            assertTrue(
                "Title sorting A-Z",
                sortedAz[i].title.lowercase() <= sortedAz[i + 1].title.lowercase()
            )
        }

        viewModel.setSortOption(SortOption.MOST_SAVED)
        val sortedSaved = viewModel.displayedPins.value
        for (i in 0 until sortedSaved.size - 1) {
            assertTrue(
                "Most saved sorting descending",
                sortedSaved[i].savesCount >= sortedSaved[i + 1].savesCount
            )
        }

        viewModel.setSortOption(SortOption.FEWEST_SAVED)
        val sortedFewestSaved = viewModel.displayedPins.value
        for (i in 0 until sortedFewestSaved.size - 1) {
            assertTrue(
                "Fewest saved sorting ascending",
                sortedFewestSaved[i].savesCount <= sortedFewestSaved[i + 1].savesCount
            )
        }

        viewModel.setSortOption(SortOption.MOST_LIKED)
        val sortedLiked = viewModel.displayedPins.value
        for (i in 0 until sortedLiked.size - 1) {
            assertTrue(
                "Most liked sorting descending",
                sortedLiked[i].likesCount >= sortedLiked[i + 1].likesCount
            )
        }
    }

    @Test
    fun `test gradual batch loading for large boards`() {
        val viewModel = PinBoardViewModel(repository)
        // Generate 100 pins
        val manyPins = (1..100).map { i ->
            PinItem(
                id = "pin_$i",
                title = "Pin #$i",
                description = "Desc",
                imageUrl = "https://example.com/$i.jpg",
                thumbnailUrl = "https://example.com/thumb_$i.jpg",
                author = "Author",
                boardName = "Big Board",
                sourceUrl = "https://pinterest.com",
                width = 500,
                height = 500,
                dateAddedMillis = 1000L + i,
                savesCount = i,
                likesCount = i,
                fileSizeKb = i.toLong()
            )
        }

        val largeBoard = createTestBoard().copy(pins = manyPins)
        viewModel.selectBoard(largeBoard)

        // Initial batch should be capped at INITIAL_BATCH_SIZE (36)
        assertEquals(100, viewModel.totalAvailablePins.value)
        assertEquals(PinBoardViewModel.INITIAL_BATCH_SIZE, viewModel.displayedPins.value.size)

        // Load next batch
        viewModel.loadNextBatch()
        assertEquals(PinBoardViewModel.INITIAL_BATCH_SIZE + PinBoardViewModel.BATCH_INCREMENT, viewModel.displayedPins.value.size)

        // Ensure visible up to index 90
        viewModel.ensureVisibleUpToIndex(90)
        assertTrue(viewModel.displayedPins.value.size >= 90)

        // Load until all pins are displayed
        viewModel.ensureVisibleUpToIndex(100)
        assertEquals(100, viewModel.displayedPins.value.size)
    }

    @Test
    fun `test date section header formats with shortened months`() {
        val cal = java.util.Calendar.getInstance().apply {
            set(2025, java.util.Calendar.SEPTEMBER, 15, 12, 0, 0)
        }
        val formatted = com.example.ui.components.formatPinDateGroup(cal.timeInMillis)
        // Should shorten September to Sep
        assertTrue("Formatted date should contain shortened month 'Sep', was: $formatted", formatted.contains("Sep"))
    }

    @Test
    fun `test hide pin titles and authors preference state`() {
        val viewModel = PinBoardViewModel(repository)
        assertFalse(viewModel.hidePinTitlesAndAuthors.value)

        viewModel.setHidePinTitlesAndAuthors(true)
        assertTrue(viewModel.hidePinTitlesAndAuthors.value)

        viewModel.setHidePinTitlesAndAuthors(false)
        assertFalse(viewModel.hidePinTitlesAndAuthors.value)
    }

    @Test
    fun `test pin model author holds creator or uploader name`() {
        val pin = PinItem(
            id = "pin_test",
            title = "Aesthetic Ceramic",
            description = "Handmade vase",
            imageUrl = "https://example.com/vase.jpg",
            thumbnailUrl = "https://example.com/vase_thumb.jpg",
            author = "StudioKanso",
            boardName = "Interior Ceramics",
            sourceUrl = "https://pinterest.com/pin/123",
            width = 800,
            height = 1200,
            dateAddedMillis = 1700000000000L,
            savesCount = 350,
            likesCount = 140,
            fileSizeKb = 420
        )
        assertEquals("StudioKanso", pin.author)
        assertEquals(800, pin.width)
        assertEquals(1200, pin.height)
    }

    @Test
    fun `test parsePinterestUrl with non-alphabet letters and special characters`() {
        // Percent-encoded Cyrillic
        val parsed1 = repository.parsePinterestUrl("https://www.pinterest.com/artlover/%D0%B4%D0%B8%D0%B7%D0%B0%D0%B9%D0%BD/")
        assertNotNull(parsed1)
        assertEquals("artlover", parsed1?.first)
        assertEquals("дизайн", parsed1?.second)

        // Raw Cyrillic domain & path
        val parsed2 = repository.parsePinterestUrl("https://ru.pinterest.com/художник/иллюстрации/")
        assertNotNull(parsed2)
        assertEquals("художник", parsed2?.first)
        assertEquals("иллюстрации", parsed2?.second)

        // Japanese board
        val parsed3 = repository.parsePinterestUrl("https://jp.pinterest.com/designer/アニメ/")
        assertNotNull(parsed3)
        assertEquals("designer", parsed3?.first)
        assertEquals("アニメ", parsed3?.second)

        // Symbols and accents with query parameters
        val parsed4 = repository.parsePinterestUrl("https://www.pinterest.com/user/anime_♡/?invite_code=abc#section")
        assertNotNull(parsed4)
        assertEquals("user", parsed4?.first)
        assertEquals("anime_♡", parsed4?.second)
    }

    @Test
    fun `test cleanSpecialText handles HTML entities, unicode escapes, and special characters`() {
        // Named entities
        val text1 = PinterestRepository.cleanSpecialText("Art &amp; Design &mdash; &quot;Inspiration&quot; &amp; Ideas")
        assertEquals("Art & Design — \"Inspiration\" & Ideas", text1)

        // Decimal numeric entities (Cyrillic дизайн)
        val text2 = PinterestRepository.cleanSpecialText("&#1076;&#1080;&#1079;&#1072;&#1081;&#1085;")
        assertEquals("дизайн", text2)

        // Hex numeric entities (Cyrillic дизайн)
        val text3 = PinterestRepository.cleanSpecialText("&#x434;&#x438;&#x437;&#x430;&#x439;&#x43d;")
        assertEquals("дизайн", text3)

        // Unicode escape sequences (\u0434\u0438\u0437\u0430\u0439\u043d)
        val text4 = PinterestRepository.cleanSpecialText("\\u0434\\u0438\\u0437\\u0430\\u0439\\u043d")
        assertEquals("дизайн", text4)

        // URL encoded sequences (%D0%B4%D0%B8%D0%B7%D0%B0%D0%B9%D0%BD)
        val text5 = PinterestRepository.cleanSpecialText("%D0%B4%D0%B8%D0%B7%D0%B0%D0%B9%D0%BD")
        assertEquals("дизайн", text5)

        // Symbols & special characters
        val text6 = PinterestRepository.cleanSpecialText("Stars &#9733;&#9734; &hearts; &#9825; &copy; 2025")
        assertEquals("Stars ★☆ ♥ ♡ © 2025", text6)

        // HTML tag stripping
        val text7 = PinterestRepository.cleanSpecialText("<p>Shared by <a href='https://example.com'>Jane Doe</a></p>")
        assertEquals("Shared by Jane Doe", text7)
    }

    @Test
    fun `test safePathEncode and safeHeaderAscii for network safety`() {
        val encoded = PinterestRepository.safePathEncode("дизайн & art")
        assertEquals("%D0%B4%D0%B8%D0%B7%D0%B0%D0%B9%D0%BD%20%26%20art", encoded)

        val asciiHeader = PinterestRepository.safeHeaderAscii("https://www.pinterest.com/art/дизайн/")
        assertTrue("Header value must be 100% ASCII", asciiHeader.all { it.code in 32..126 })
    }

    @Test
    fun `test newest added sorting orders by board position and date added`() {
        val viewModel = PinBoardViewModel(repository)

        val now = System.currentTimeMillis()
        val oldPin1 = PinItem(
            id = "old1",
            title = "Old Pin 1",
            description = "",
            imageUrl = "https://i.pinimg.com/736x/old1.jpg",
            thumbnailUrl = "https://i.pinimg.com/236x/old1.jpg",
            author = "creator",
            boardName = "Board",
            sourceUrl = "",
            width = 500,
            height = 500,
            boardPosition = 3,
            dateAddedMillis = now - (20L * 24 * 60 * 60 * 1000L)
        )
        val oldPin2 = PinItem(
            id = "old2",
            title = "Old Pin 2",
            description = "",
            imageUrl = "https://i.pinimg.com/736x/old2.jpg",
            thumbnailUrl = "https://i.pinimg.com/236x/old2.jpg",
            author = "creator",
            boardName = "Board",
            sourceUrl = "",
            width = 500,
            height = 500,
            boardPosition = 2,
            dateAddedMillis = now - (15L * 24 * 60 * 60 * 1000L)
        )
        val freshPin1 = PinItem(
            id = "fresh1",
            title = "Fresh Pin 1",
            description = "",
            imageUrl = "https://i.pinimg.com/736x/fresh1.jpg",
            thumbnailUrl = "https://i.pinimg.com/236x/fresh1.jpg",
            author = "creator",
            boardName = "Board",
            sourceUrl = "",
            width = 500,
            height = 500,
            boardPosition = 1,
            dateAddedMillis = now - (5L * 24 * 60 * 60 * 1000L)
        )
        val freshPin2 = PinItem(
            id = "fresh2",
            title = "Fresh Pin 2",
            description = "",
            imageUrl = "https://i.pinimg.com/736x/fresh2.jpg",
            thumbnailUrl = "https://i.pinimg.com/236x/fresh2.jpg",
            author = "creator",
            boardName = "Board",
            sourceUrl = "",
            width = 500,
            height = 500,
            boardPosition = 0,
            dateAddedMillis = now - (1L * 24 * 60 * 60 * 1000L)
        )

        val board = PinterestBoard(
            id = "board-test",
            title = "Test Board",
            slug = "test-board",
            ownerUsername = "user",
            ownerDisplayName = "User",
            ownerAvatarUrl = "",
            pinCount = 4,
            followerCount = 0,
            boardUrl = "https://pinterest.com/user/test-board",
            description = "",
            pins = listOf(oldPin1, oldPin2, freshPin1, freshPin2)
        )

        viewModel.selectBoard(board)
        viewModel.setSortOption(SortOption.DATE_NEWEST)

        val displayed = viewModel.displayedPins.value
        assertEquals("fresh2", displayed[0].id)
        assertEquals("fresh1", displayed[1].id)
        assertEquals("old2", displayed[2].id)
        assertEquals("old1", displayed[3].id)
    }

    @Test
    fun `test browserless two pass extraction picks OpenGraph header image over logo and avatar`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Breaking Tech News - Leading Story</title>
                <meta property="og:title" content="Breaking Tech News" />
                <meta property="og:image" content="https://news.example.com/uploads/2026/hero-lead.jpg" />
                <meta name="twitter:image" content="https://news.example.com/uploads/2026/twitter-lead.jpg" />
            </head>
            <body>
                <header>
                    <img src="https://news.example.com/assets/logo.png" alt="Company Logo" class="brand-logo" />
                </header>
                <article>
                    <img src="https://news.example.com/assets/avatar_author.jpg" alt="Author avatar" />
                    <img src="https://news.example.com/uploads/2026/content-image.jpg" class="article-image" />
                    <img src="https://tracker.com/pixel.gif" />
                </article>
            </body>
            </html>
        """.trimIndent()

        val candidate = com.example.util.ImageLinkResolver.extractMainImageTwoPass(html, "https://news.example.com/article/123")
        assertNotNull("Should extract a main image", candidate)
        assertEquals("https://news.example.com/uploads/2026/hero-lead.jpg", candidate?.url)
        assertTrue("Preliminary score should be positive and high", (candidate?.preliminaryScore ?: 0f) > 50f)
    }

    @Test
    fun `test browserless two pass extraction picks JSON-LD schema image`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "NewsArticle",
                    "headline": "Major Breakthrough Announced",
                    "image": "https://example.com/news/breakthrough-header.webp"
                }
                </script>
            </head>
            <body>
                <img src="/assets/icon_badge.png" />
            </body>
            </html>
        """.trimIndent()

        val candidate = com.example.util.ImageLinkResolver.extractMainImageTwoPass(html, "https://example.com/story")
        assertNotNull(candidate)
        assertEquals("https://example.com/news/breakthrough-header.webp", candidate?.url)
    }

    @Test
    fun `test browserless two pass extraction handles imageboard full image`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <body>
                <div class="fileText">File: <a href="//i.4cdn.org/g/1700000000123.jpg">full_artwork.jpg</a></div>
                <a class="fileThumb" href="//i.4cdn.org/g/1700000000123s.jpg">
                    <img src="//i.4cdn.org/g/1700000000123s.jpg" />
                </a>
            </body>
            </html>
        """.trimIndent()

        val candidate = com.example.util.ImageLinkResolver.extractMainImageTwoPass(html, "https://boards.4channel.org/g/thread/1234")
        assertNotNull(candidate)
        assertEquals("https://i.4cdn.org/g/1700000000123.jpg", candidate?.url)
    }

    @Test
    fun `test relative URL resolution in ImageLinkResolver`() {
        val resolved = com.example.util.ImageLinkResolver.resolveAbsoluteUrl(
            "https://myblog.com/posts/travel-guide",
            "/media/summer-hero.jpg"
        )
        assertEquals("https://myblog.com/media/summer-hero.jpg", resolved)
    }

    @Test
    fun `test custom board pins sort newest first and older last`() {
        val p1 = PinItem(id = "1", title = "P1", imageUrl = "url1", dateAddedMillis = 1000L, boardPosition = 1)
        val p2 = PinItem(id = "2", title = "P2", imageUrl = "url2", dateAddedMillis = 2000L, boardPosition = 2)
        val p3 = PinItem(id = "3", title = "P3", imageUrl = "url3", dateAddedMillis = 500L, boardPosition = 0)
        val list = listOf(p1, p2, p3)
        val sorted = list.sortedWith(
            compareByDescending<PinItem> { it.dateAddedMillis }.thenBy { it.boardPosition }
        )
        assertEquals("2", sorted[0].id)
        assertEquals("1", sorted[1].id)
        assertEquals("3", sorted[2].id)
    }

    @Test
    fun `test date album grouping by day`() {
        val day1 = 1700000000000L
        val day2 = day1 + 86400000L * 2
        val p1 = PinItem(id = "1", title = "P1", imageUrl = "url1", dateAddedMillis = day1)
        val p2 = PinItem(id = "2", title = "P2", imageUrl = "url2", dateAddedMillis = day1 + 1000L)
        val p3 = PinItem(id = "3", title = "P3", imageUrl = "url3", dateAddedMillis = day2)
        val pins = listOf(p1, p2, p3)

        val dayFormatter = java.text.SimpleDateFormat("yyyyMMdd", java.util.Locale.US)
        val map = linkedMapOf<String, MutableList<PinItem>>()
        for (pin in pins) {
            val key = dayFormatter.format(java.util.Date(pin.dateAddedMillis))
            map.getOrPut(key) { mutableListOf() }.add(pin)
        }
        val albums = map.entries.map { (key, pinsList) ->
            com.example.model.DateAlbum(
                id = "day_$key",
                title = key,
                isMonthly = false,
                pins = pinsList.toList(),
                dateMillis = pinsList.first().dateAddedMillis
            )
        }
        assertEquals(2, albums.size)
        assertEquals(2, albums[0].pins.size)
        assertEquals(1, albums[1].pins.size)
    }

    @Test
    fun `test individually favorited pins preserved when album is unfavorited`() {
        val p1 = PinItem(id = "pin_indiv", title = "P1", imageUrl = "url1")
        val p2 = PinItem(id = "pin_album_only", title = "P2", imageUrl = "url2")
        val albumPins = listOf(p1, p2)

        val indivFavKeys = setOf("pin_indiv", "url1")
        var currentFavKeys = setOf("pin_indiv", "url1", "pin_album_only", "url2")

        // Album is unfavorited: remove only pins NOT in individual favorite keys
        val pinsToRemove = albumPins.filterNot { pin ->
            indivFavKeys.contains(pin.id) || indivFavKeys.contains(pin.imageUrl)
        }
        val removedKeys = pinsToRemove.flatMap { listOf(it.id, it.imageUrl) }.toSet()
        currentFavKeys = currentFavKeys - removedKeys

        // p1 must still be favorited!
        assertTrue(currentFavKeys.contains(p1.id))
        // p2 must be removed from favorites
        assertFalse(currentFavKeys.contains(p2.id))
    }
}

