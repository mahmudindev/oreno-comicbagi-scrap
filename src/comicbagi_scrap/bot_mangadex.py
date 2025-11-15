import time
import logging
import comicbagi_openapi
import mangadex_openapi
import comicking_scrap
from datetime import datetime
from typing import Iterable
from urllib.parse import quote

from .bot import Bot

class BotMangaDex:
    website_mangadex_host = 'mangadex.org'

    def __init__(
        self,
        bot: Bot,
        comicking_jikan_bot: comicking_scrap.BotJikan | None,
        logger: logging.Logger
    ):
        from mangadex_openapi.api_client import ApiClient as MangaDexApiClient

        self.bot = bot
        self.client = MangaDexApiClient()

        self.comicking_jikan_bot = comicking_jikan_bot

        self.logger = logger

    def load(self, seeding: bool = True):
        if seeding:
            self.bot.authenticate()

        #
        # Website
        #

        api0 = comicbagi_openapi.WebsiteApi(self.bot.client)

        if self.website_mangadex_host not in self.bot.websites:
            try:
                api0.get_website(self.website_mangadex_host)

                self.bot.websites.append(self.website_mangadex_host)
            except comicbagi_openapi.ApiException as e:
                if seeding and e.status == 404:
                    self.bot.add_website(self.website_mangadex_host, 'MangaDex', True)

                    time.sleep(2)
                else:
                    raise e

    def note(self, __lines: Iterable[str] | None = None):
        if __lines:
            self.logger.info(__lines)
            if self.bot.note_file: self.bot.note_file.writelines(__lines)

        if self.bot.note_file: self.bot.note_file.writelines("\n")

    def process(
        self,
        mode: str = 'comic',
        max_new_comic: int | None = None,
        max_new_comic_chapter: int | None = None
    ):
        self.note('#')
        self.note('# Started time %s' % time.ctime())
        self.note('#')
        self.note()

        self.load(True)

        self.scrap_comics_complete(mode, max_new_comic, max_new_comic_chapter)

        self.note()
        self.note('# Stopped time %s' % time.ctime())
        self.note()

    def __manga(self, manga: mangadex_openapi.Manga):
        comic_code, comic_exist = None, False

        if not manga.id:
            return comic_code, comic_exist

        manga_attributes = manga.attributes

        if not manga_attributes or not manga_attributes.available_translated_languages:
            return comic_code, comic_exist

        manga_language_supported = False

        for manga_language in manga_attributes.available_translated_languages:
            if manga_language in self.bot.languages:
                manga_language_supported = True
                break

        if not manga_language_supported:
            return comic_code, comic_exist

        self.bot.authenticate()

        # Comic

        api0 = comicbagi_openapi.ComicApi(self.bot.client)

        response0 = api0.list_comic(
            provider_link_href=[quote(f'{self.website_mangadex_host}/title/{manga.id}')]
        )

        api1 = comicbagi_openapi.LinkApi(self.bot.client)

        if len(response0) < 1:
            if manga_attributes.links:
                for k, v in manga_attributes.links.items():
                    if comic_code:
                        break

                    match k:
                        case 'mal':
                            self.note('=== ComicKing Scrap ===')

                            if not self.comicking_jikan_bot:
                                continue

                            comic_code = self.comicking_jikan_bot.get_or_add_comic_complete(int(v))

                            self.note('=== ComicKing Scrap ===')

                            time.sleep(3)
                        case _:
                            continue

            if not comic_code:
                self.note('No information provider supported.')
                return comic_code, comic_exist

            try:
                api0.get_comic(comic_code)
            except comicbagi_openapi.ApiException as e:
                if e.status == 404:
                    self.bot.add_comic(comic_code)

                    time.sleep(2)
                else:
                    raise e

            # Comic Provider

            comic_link = f'{self.website_mangadex_host}/title/{manga.id}'

            try:
                api1.get_link(comic_link)
            except comicbagi_openapi.ApiException as e:
                if e.status == 404:
                    self.bot.add_link(self.website_mangadex_host, f'/title/{manga.id}')

                    time.sleep(2)
                else:
                    raise e

            response01 = api0.list_comic_provider(comic_code, link_href=[quote(comic_link)])

            for manga_language in manga_attributes.available_translated_languages:
                if manga_language not in self.bot.languages:
                    continue

                comic_provider_exist = False
                for comic_provider in response01:
                    if manga_language == comic_provider.language_lang:
                        comic_provider_exist = True
                        break

                if comic_provider_exist:
                    continue

                comic_released_at = datetime.now()
                if manga_attributes.created_at:
                    comic_released_at = datetime.fromisoformat(manga_attributes.created_at)

                self.bot.add_comic_provider(
                    comic_code,
                    self.website_mangadex_host,
                    f'/title/{manga.id}',
                    manga_language,
                    comic_released_at
                )

                time.sleep(2)
        else:
            if len(response0) > 1:
                self.note('Detected multiple comic with same MangaDex ID %s' % manga.id)

            comic_code, comic_exist = response0[0].code, True

        return comic_code, comic_exist

    def __manga_chapter(self, comic_code: str, chapter: mangadex_openapi.Chapter):
        chapter_nv, chapter_exist = None, False

        if not chapter.id:
            return chapter_nv, chapter_exist

        chapter_attributes = chapter.attributes

        if not chapter_attributes or not chapter_attributes.chapter:
            return chapter_nv, chapter_exist

        chapter_language = chapter_attributes.translated_language

        if not chapter_language or chapter_language not in self.bot.languages:
            return chapter_nv, chapter_exist

        api0 = comicbagi_openapi.ComicChapterApi(self.bot.client)

        # Chapter

        chapter_number = float(chapter_attributes.chapter)
        try:
            chapter_number = int(chapter_attributes.chapter)
        except ValueError:
            pass

        if f'{comic_code} {chapter_number}' not in self.bot.comic_chapters:
            try:
                api0.get_comic_chapter(comic_code, str(chapter_number))

                self.bot.comic_chapters.append(f'{comic_code} {chapter_number}')

                chapter_exist = True
            except comicbagi_openapi.ApiException as e:
                if e.status == 404:
                    self.bot.add_comic_chapter(
                        comic_code,
                        chapter_number,
                        None
                    )

                    time.sleep(2)
                else:
                    raise e

        chapter_nv = str(chapter_number)

        # Chapter Provider

        api1 = comicbagi_openapi.LinkApi(self.bot.client)

        chapter_link = quote(f'{self.website_mangadex_host}/chapter/{chapter.id}')

        try:
            api1.get_link(chapter_link)
        except comicbagi_openapi.ApiException as e:
            if e.status == 404:
                self.bot.add_link(self.website_mangadex_host, f'/chapter/{chapter.id}')

                time.sleep(2)
            else:
                raise e

        response = api0.list_comic_chapter_provider(
            comic_code,
            chapter_nv,
            link_href=[quote(chapter_link)]
        )

        chapter_provider_exist = False
        for chapter_provider in response:
            if chapter_attributes.translated_language == chapter_provider.language_lang:
                chapter_provider_exist = True
                break

        if not chapter_provider_exist:
            chapter_released_at = datetime.now()
            if chapter_attributes.created_at:
                chapter_released_at = datetime.fromisoformat(chapter_attributes.created_at)

            self.bot.add_comic_chapter_provider(
                comic_code,
                chapter_nv,
                self.website_mangadex_host,
                f'/chapter/{chapter.id}',
                chapter_attributes.translated_language,
                chapter_released_at
            )

            time.sleep(2)

        return chapter_nv, chapter_exist

    def scrap_comics_complete(
        self,
        mode: str = 'comic',
        max_comic: int | None = None,
        max_comic_chapter: int | None = None
    ):
        api1 = mangadex_openapi.MangaApi(self.client)
        api2 = mangadex_openapi.ChapterApi(self.client)

        total_comic = 0

        page = 1
        while True:
            if max_comic and total_comic > max_comic - 1:
                break

            match mode:
                case 'comic-chapter':
                    response = api2.get_chapter(
                        limit=30,
                        offset=(page-1)*30,
                        include_future_updates='0',
                        include_empty_pages=0
                    )
                    if not response.data:
                        break

                    for comic_chapter in response.data:
                        if max_comic and total_comic > max_comic - 1:
                            break

                        if not comic_chapter.id:
                            continue

                        self.note()
                        self.note('Check MangaDex chapter ID %s' % comic_chapter.id)

                        manga_id = None
                        if comic_chapter.relationships:
                            for relationship in comic_chapter.relationships:
                                if relationship.type == 'manga':
                                    manga_id = relationship.id
                                    break
 
                        if not manga_id:
                            continue

                        self.note('Check MangaDex manga ID %s' % manga_id)

                        response1 = api1.get_manga_id(manga_id)
                        if not response1.data:
                            continue

                        comic_code, comic_exist = self.__manga(response1.data)
                        time.sleep(3)

                        self.note("MangaDex manga ID %s check complete" % manga_id)

                        if comic_code:
                            self.__manga_chapter(comic_code, comic_chapter)

                        self.note("MangaDex chapter ID %s check complete" % comic_chapter.id)
                        self.note()

                        if comic_code and not comic_exist:
                            total_comic += 1
                            time.sleep(5)
                case _:
                    response = api1.get_search_manga(
                        limit=10,
                        offset=(page-1)*10,
                        has_available_chapters='1'
                    )
                    if not response.data:
                        break

                    for manga in response.data:
                        if max_comic and total_comic > max_comic - 1:
                            break

                        if not manga.id:
                            continue

                        self.note()
                        self.note('Check MangaDex manga ID %s' % manga.id)

                        comic_code, comic_exist = self.__manga(manga)
                        time.sleep(3)

                        if comic_code:
                            total_comic_chapter = 0

                            page1 = 1
                            while True:
                                if max_comic_chapter and total_comic_chapter > max_comic_chapter - 1:
                                    break

                                response1 = api1.get_manga_id_feed(
                                    manga.id,
                                    limit=30,
                                    offset=(page1-1)*30,
                                    include_future_updates='0',
                                    include_empty_pages=0
                                )
                                if not response1.data:
                                    break

                                for comic_chapter in response1.data:
                                    if max_comic_chapter and total_comic_chapter > max_comic_chapter - 1:
                                        break

                                    if not comic_chapter.id:
                                        continue

                                    self.note('Check MangaDex chapter ID %s' % comic_chapter.id)

                                    comic_chapter_nv, comic_chapter_exist = self.__manga_chapter(
                                        comic_code,
                                        comic_chapter
                                    )

                                    self.note("MangaDex chapter ID %s check complete" % comic_chapter.id)

                                    if comic_chapter_nv or not comic_chapter_exist:
                                        total_comic_chapter += 1
                                        time.sleep(5)

                                page1 += 1
                                time.sleep(3)

                        self.note("MangaDex manga ID %s check complete" % manga.id)
                        self.note()

                        if comic_code and not comic_exist:
                            total_comic += 1
                            time.sleep(5)

            page += 1
            time.sleep(3)
