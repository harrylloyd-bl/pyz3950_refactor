"""
Removed any data processing prior to delivery of cards_df to simplify env for streamlit
Will need to prepare elsewhere then pull in as pickle or csv
"""

import re
import os
import pickle
import xml.etree.ElementTree as ET
from PIL import Image
import pandas as pd
import streamlit as st
import requests

cards_df = pickle.load(open("notebooks/cards_df.p", "rb"))
# cards_df["xml"] = cards_df["xml"].str.decode("utf-8")

nulls = len(cards_df) - len(cards_df.dropna(subset="worldcat_result"))
errors = len(cards_df.query("worldcat_result == 'Error'"))
cards_to_show = cards_df.query("worldcat_result != 'Error'").dropna(subset="worldcat_result")
st.markdown("# Worldcat results for searches for catalogue card title/author")
st.write(f"\nTotal of {len(cards_df)} cards")
st.write(f"Showing {len(cards_to_show)} cards with Worldcat results, omitting {nulls} without results and {errors} with errors in result retrieval")
st.dataframe(cards_to_show.loc[:, ("title", "author", "shelfmark", "worldcat_result", "lines")])

option = st.selectbox(
    "Which result set do you want to choose between?",
    pd.Series(cards_to_show.index, index=cards_to_show.index, dtype=str) + " ti: " + cards_to_show["title"] + " au: " + cards_to_show["author"]
)
"Current selection: ", option

# p5_root = (
#     "G:/DigiSchol/Digital Research and Curator Team/Projects & Proposals/00_Current Projects"
#     "/LibCrowds Convert-a-Card (Adi)/OCR/20230504 TKB Export P5 175 GT pp/1016992/P5_for_Transkribus"
# )

idx = int(option.split(" ")[0])
card_jpg_path = os.path.join("data/images", cards_to_show.loc[idx, "xml"][:-4] + ".jpg")

st.image(Image.open(card_jpg_path))

st.markdown("## Select from worldcat results")
search_term = f"https://www.worldcat.org/search?q=ti%3A{cards_to_show.loc[idx, 'title'].replace(' ', '+')}+AND+au%3A{cards_to_show.loc[idx, 'author'].replace(' ', '+')}"
st.markdown(f"You can also check the [Worldcat search]({search_term}) for this card")
match_df = pd.DataFrame({"record": list(cards_to_show.loc[idx, "worldcat_result"].values())})

lang_xml = requests.get("https://www.loc.gov/standards/codelists/languages.xml")
tree = ET.fromstring(lang_xml.text)
lang_dict = {lang[2].text: lang[1].text for lang in tree[4]}

lang_040b_re = re.compile("\$b[a-z]+\$")
match_df["language_040$b"] = match_df["record"].apply(lambda x: lang_040b_re.search(x.get_fields("040")[0].__str__()).group())
match_df["language"] = match_df["language_040$b"].str[2:-1].map(lang_dict)

lang_select = st.radio(
    "Select Cataloguing Language (040 $b)",
    match_df["language"].unique()
)

matches_to_show = match_df.query("language == @lang_select")
es = "es" if len(matches_to_show) > 1 else ""
st.write(f"{len(matches_to_show)} {lang_select} match{es}")
input_max = st.number_input("Max records to display", min_value=1)
if input_max <= len(matches_to_show):
    max_to_display = int(input_max)
else:
    max_to_display = len(matches_to_show)


def gen_unique_idx(df):
    df["Repeat Field ID"] = ""
    dup_idx = df.index[df.index.duplicated()].unique()
    unhandled_fields = [x for x in dup_idx if x not in [500, 650, 880]]
    if 500 in dup_idx:
        df.loc[500, "Repeat Field ID"] = [str(x) for x in range(len(df.loc[500]))]
    if 650 in dup_idx:
        df.loc[650, "Repeat Field ID"] = df.loc[650, df.columns[0]].str.split(" ").transform(lambda x: x[0])
    if 880 in dup_idx:
        df.loc[880, "Repeat Field ID"] = df.loc[880, df.columns[0]].str.split("/").transform(lambda x: x[0])
    for dup in unhandled_fields:
        df.loc[dup, "Repeat Field ID"] = [str(x) for x in range(len(df.loc[dup]))]
    return df.set_index("Repeat Field ID", append=True)


cols = []
for i in range(max_to_display):
    res = match_df.iloc[i-1, 0].get_fields()
    col = pd.DataFrame(
        index=pd.Index([int(x.tag) for x in res], name="MARC Field"),
        data=[x.__str__()[6:] for x in res],
        columns=[i+1]
    )
    cols.append(gen_unique_idx(col))

st.dataframe(pd.concat(cols, axis=1).sort_index())

# cols = st.columns(max_to_display)
#
# for i, c in enumerate(cols):
#     with c:
#         res = matches_to_show.iloc[i-1, 0].get_fields()
#         st.dataframe(pd.DataFrame(
#             index=[int(x.tag) for x in res],
#             data=[x.__str__()[6:] for x in res],
#             columns=[i]))

good_res = st.radio(
    "Which is the correct Worldcat result?",
    (*range(1, max_to_display+1), "None of the results are correct")
)