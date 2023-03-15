import asyncio
from utils.scraping import Scraping

if __name__ == '__main__':
    scraping = Scraping("https://www.classcentral.com")
    html = asyncio.run(scraping.main())
