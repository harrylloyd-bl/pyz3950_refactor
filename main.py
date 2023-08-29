from __future__ import annotations

import glob
import os
import re
import pickle
import xml.etree.ElementTree as ET
from tqdm import tqdm
import pandas as pd
from src.data import oclc

LOAD_XMLS = False
LOAD_PICKLE = False

smark_regex = re.compile("[0-9]{1,5}[\s\.]{1,2}[\w]{1,3}[\s\.]{1,2}[\w0-9]{1,5}")
author_regex = re.compile("[A-Z]+[\s]+\([A-Z][a-z]+\)")
isbn_regex = re.compile("ISBN\s[0-9\-\s]+")


def extractLines(root: ET.Element):
    lines = []

    textRegions = [x for x in root[1] if len(x) > 2]  # Empty Text Regions Removed

    for textRegion in textRegions:
        textLines = textRegion[1:-1]  # Skip coordinate data in first child
        for textLine in textLines:
            lines.append(textLine[-1][0].text)  # Text equivalent for line
    return lines


def extractLinesForVol(vol: list[ET.Element]):
    allLines = []
    for root in tqdm(vol):
        rootLines = extractLines(root)
        allLines.append(rootLines)
    return allLines


def find_author(lines, dummy):
    author, title = None, None

    for i, l in enumerate(lines):
        if author_regex.search(l):  # look for an author format match
            author = l
            break

    if author:
        if i >= 2:  # author is after the second line (where we expect the title)
            title = " ".join(lines[1:i])
        elif i == 1:  # author is the second line
            title = lines[2]
    else:
        title = lines[1]  # default to the title being the second line

    return title, author


def isbn_search(x):
    res = isbn_regex.search(x)
    if res:
        return res.group()
    else:
        return None


p5_root = (
    r"G:\DigiSchol\Digital Research and Curator Team\Projects & Proposals\00_Current Projects"
    r"\LibCrowds Convert-a-Card (Adi)\OCR\20230504 TKB Export P5 175 GT pp\1016992\P5_for_Transkribus"
)

if LOAD_XMLS:
    page_xml_loc = os.path.join(p5_root, "page")

    attempts = 0
    while attempts < 3:
        xmls = glob.glob(os.path.join(page_xml_loc, "*.xml"))
        if len(xmls) > 0:
            break
        else:
            attempts += 1
            continue
    else:
        raise IOError(f"Failed to connect to {page_xml_loc}")

    xmlroots = []

    print(f"\nGetting xml roots from {page_xml_loc}")
    for file in tqdm(xmls):
        fileName = os.fsdecode(file)
        attempts = 0
        while attempts < 3:
            try:
                tree = ET.parse(fileName)
                break
            except FileNotFoundError:
                attempts += 1
                continue
        else:
            raise FileNotFoundError(f"Failed to connect to: {fileName}")
        root = tree.getroot()
        xmlroots.append(root)

    cards = extractLinesForVol(xmlroots)
    cards_df_v0 = pd.DataFrame(
        data={
            "xml": [os.path.basename(x) for x in xmls],
            "lines": cards,
            "dummy": [None for x in cards]
        }
    )

    cards_df_v0["shelfmark"] = cards_df_v0["lines"].transform(lambda x: smark_regex.search(x[0]).group()).str.replace(" ", "")
    t_a = cards_df_v0.loc[:,('lines', 'dummy')].transform(lambda x: find_author(x[0], x[1]), axis=1).rename(columns={"lines":"title", "dummy":"author"})
    cards_df = cards_df_v0.drop(columns="dummy").join(t_a)
    cards_df["ISBN"] = cards_df["lines"].transform(lambda x:isbn_search("".join(x))).str.replace("ISBN ", "").str.strip()

    res = pickle.load(open("notebooks\\res.p", "rb"))
    cards_df['worldcat_result'] = res

    with open("notebooks\\cards_df.p", "wb") as f:
        pickle.dump(cards_df, f)

if LOAD_PICKLE:
    cards_df = pickle.load(open("notebooks\\cards_df.p", "rb"))
    # cards_df["xml"] = cards_df["xml"].str.decode("utf-8")


# res_dict, res = oclc.OCLC_query("FENG JIAN ZHU YI DE SHENG CHAN FANG SHI", "ZHANG (Yu)")
# 34 records in blocks of 17
seventeen_result = oclc.OCLC_query(title="FAN SHEN JI SHI", author="LIANG (Bin)")
# 24 records in blocks of 8
eight_result = oclc.OCLC_query(title="FENG CUN XIAO SHUO XUAN", author="FENG (Cun)")
# 60 records in blocks of 20
twenty_result = oclc.OCLC_query(title="Feng huang", author="SHEN (Congwen)")
# print(result[0])
print("hello")
