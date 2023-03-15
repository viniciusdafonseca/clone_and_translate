import os
import re
from pathlib import Path
from typing import List

import aiofiles
from bs4 import BeautifulSoup
from englisttohindi.englisttohindi import EngtoHindi
from httpx import AsyncClient
from loguru import logger


class Scraping:
    def __init__(self, base_url: str):
        self._base_url = base_url
        self._path = "/home/vinicius/PycharmProjects/turkish_challenge/pages"

        self._session = AsyncClient(timeout=30, follow_redirects=True)
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,"
                      "*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "accept-encoding": "gzip, deflate",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/83.0.4103.97 Safari/537.36",
        }
        self._session.headers.update(headers)
        self._session.base_url = base_url

    async def main(self) -> None:
        soup = await self.get_html_from_url()
        all_tags = await self._get_ahref_from_soup(soup)
        await self._acessing_one_level_page(all_tags)

    async def _treats_html(self, response_text: str) -> BeautifulSoup:
        """
        Treats all tags with href, src, etc and translate it
        :param response_text: html text
        :return: soup: BeautifulSoup - translated html page
        """
        soup = BeautifulSoup(response_text, 'html.parser')

        imgs = soup.find_all('img', {"data-src": True})
        for img in imgs:
            img["src"] = img["data-src"]

        links = soup.find_all('link')
        for link in links:
            if not re.search(r"rel", str(link)):
                continue

            if link["rel"] == "canonical":
                continue

            if self._base_url in link["href"]:
                continue

            link["href"] = f"https://www.classcentral.com{link['href'].replace(self._base_url, '')}"

        scripts = soup.find_all('script', {"src": True})[1:]
        for script in scripts:
            if self._base_url in script["src"]:
                continue

            script["src"] = f"https://www.classcentral.com{script['src'].replace(self._base_url, '')}"

        all_tags = await self._get_ahref_from_soup(soup)
        for tag in all_tags:
            tag["href"] = tag["href"].strip().replace(self._base_url, "")

        return await self._translate_en_to_hindi(soup)

    @staticmethod
    async def _join_2_texts_tags(text_list: List) -> List[str]:
        """
        Join two tags in one, making less calls to translate function
        :param text_list: list with text
        :return: hindi_text_list: List[str] - list with hindi text
        """
        hindi_text_list = []

        two_texts_lists = [text_list[i:i + 4] for i in range(0, len(text_list), 4)]
        cont = 1
        for two_texts in two_texts_lists:
            two_texts_splited = '|-|'.join(two_texts)
            two_texts_hindi = EngtoHindi(two_texts_splited).convert

            cont += 1
            if len(two_texts) != len(two_texts_hindi.split("|-|")) or len(two_texts_splited) >= 235:
                for text in two_texts:
                    text_hindi = EngtoHindi(text).convert
                    hindi_text_list.append(text_hindi)

                continue

            hindi_text_list.append(two_texts_hindi)

        return hindi_text_list

    async def _translate_en_to_hindi(self, soup: BeautifulSoup) -> BeautifulSoup:
        """
        Translate the html from english to hindi.
        :param soup: html page
        :return: soup: BeautifulSoup - hindi html page
        """
        logger.info("TRANSLATING HTML...")

        text_list = []
        all_tags = soup.find_all(text=True)
        for tag in all_tags:
            text = tag.get_text().strip()
            if text == "":
                continue

            # gets the last children tag
            last_tag = BeautifulSoup(text, "html.parser").find_all()
            if last_tag:
                text = last_tag[-1].get_text().strip()

            text_list.append(text)

        hindi_text_list = await self._join_2_texts_tags(text_list)
        hindi_text_splitted = '|-|'.join(hindi_text_list).split('|-|')

        # replace the english text to hindi text
        index = 0
        for tag in all_tags:
            text = tag.get_text().strip()
            if text == "":
                continue

            hindi_string = hindi_text_splitted[index]
            tag.string.replace_with(hindi_string)
            index += 1

        logger.info("HTML TRANSLATED!")
        return soup

    async def get_html_from_url(self) -> BeautifulSoup:
        """
        Colect and saves the home page.
        :return: soup: BeautifulSoup - home page html
        """
        logger.info(f"{self._base_url} - COLECTING HOME PAGE...")
        response = await self._session.get(self._base_url)
        soup = await self._treats_html(response.text)

        filename = f"{self._path}/index.html"
        async with aiofiles.open(filename, "w") as file:
            await file.write(str(soup))

        logger.info(f"HOME PAGE FINISHED!")
        return soup

    @staticmethod
    async def _get_ahref_from_soup(soup: BeautifulSoup) -> List[BeautifulSoup]:
        """
        Gets all `a` tags needed.
        :param soup: html page
        :return: tag: List[BeautifulSoup] - all tags needed
        """
        all_tags = soup.find_all("a", {"href": True, "rel": False})
        tags = []
        for tag in all_tags:
            if re.search(r"data-track-click=\"nav_click\"", str(tag)) is not None:  # ignores tag from the home page dropdown
                continue

            tags.append(tag)

        return tags

    @staticmethod
    async def _create_folder(href: str) -> tuple:
        """
        Creates folder from file path.
        :param href: complement path for file
        :return: filename: str, filename_exists: bool - filename from `href` and if the files already exists
        """
        if href.count("/") == 1:  # identifies if the file is a index of the directory
            href = f"{href}/index"
        elif href.count("/") == 3:  # identifies whether a previous path needs to be created
            path = '/'.join(href.split('/')[0:-2])
            path = f"{str(Path().absolute())}/pages{path}"
            if not os.path.exists(path):
                logger.debug(f"NEW PATH - Creating {path}...")
                os.mkdir(path)

        filename = f"{str(Path().absolute())}/pages{href}.html"
        if os.path.exists(filename):
            return filename, True

        path = '/'.join(filename.split('/')[0:-1])
        if not os.path.exists(path):
            logger.debug(f"NEW PATH - Creating {path}...")
            os.mkdir(path)

        return filename, False

    async def _acessing_one_level_page(self, all_tags: List[BeautifulSoup]) -> None:
        """
        Acess all one level pages from home url.
        :param all_tags: all `a` tags founds in the homepage
        :return:
        """
        cont = 0
        for tag in all_tags:
            cont += 1

            href = tag["href"].strip().replace(self._base_url, "")
            if href == "/" or re.search(r"email-protection", href):  # skips the home page and some exception page
                logger.error(f"{cont} / {len(all_tags)} - HOME PAGE ALREADY COLECTED! -  SKIPING...")
                continue

            if href[-1] == "/":  # removes last bar from href
                href = href[:-1]

            # creates the folder in directory `pages`, also verifies if the file already exists
            filename, filename_exists = await self._create_folder(href)
            if filename_exists:
                logger.error(f"{cont} / {len(all_tags)} - {filename} PAGE ALREADY COLECTED! - SKIPING...")
                continue

            logger.info(f"{cont} / {len(all_tags)} - {filename} COLECTING...")

            # make the requisition to the url page and treats the html
            response = await self._session.get(href)
            soup = await self._treats_html(response.text)

            async with aiofiles.open(filename, "w") as file:
                await file.write(str(soup))

            logger.info(f"{cont} / {len(all_tags)} - {filename} FINISHED!")
