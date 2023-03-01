This repo created by Giorgia Tolfo and picked up by Harry LLoyd, readme by HL.

This repo is part of the Convert-a-Card project to convert catalogue cards, primarily from the Asian and African Studies Reading Room at the BL.
Code here consumes xml files produced from card transcription by [Transkribus] (lite.transkribus.eu), parses the xml to extract card title/author/shelfmark the queries [OCLC Worldcat] (https://www.worldcat.org/) to see if a matching record exists.

Structure
| --- urdu_cards_pages\	<- xml files of urdu catalogue cards exported from Transkribus
|
| --- z3950\		<- holds the PyZ3950 python package used to query Worldcat using Z39.50 standard
|
| --- cards-xml2csv.ipynb <- jupyter nb with main code to parse xml and search Worldcat
|
| --- environment.yml	<- conda/mamba environment, recreated via e.g. conda create -f environment.yml
|
| --- readme.md		<- top-level info for the project