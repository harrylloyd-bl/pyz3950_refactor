"""
Removed any data processing prior to delivery of cards_df to simplify env for streamlit
Will need to prepare elsewhere then pull in as pickle or csv
"""

import os
import pickle
from PIL import Image
import pandas as pd
import streamlit as st

LOAD_PICKLE = True
if LOAD_PICKLE:
    cards_df = pickle.load(open("notebooks/cards_df.p", "rb"))
    # cards_df["xml"] = cards_df["xml"].str.decode("utf-8")

nulls = len(cards_df) - len(cards_df.dropna(subset="worldcat_result"))
errors = len(cards_df.query("worldcat_result == 'Error'"))
to_show = cards_df.query("worldcat_result != 'Error'").dropna(subset="worldcat_result")
st.markdown("# Worldcat results for searches for catalogue card title/author")
st.write(f"\nTotal of {len(cards_df)} cards")
st.write(f"Showing {len(to_show)} cards with Worldcat results, omitting {nulls} without results and {errors} with errors in result retrieval")
st.dataframe(to_show.loc[:,("title", "author", "shelfmark", "worldcat_result", "lines")])

option = st.selectbox(
    "Which result set do you want to choose between?",
    pd.Series(to_show.index, index=to_show.index, dtype=str) + " ti: " + to_show["title"] + " au: " + to_show["author"]
)
"Current selection: ", option

# p5_root = (
#     "G:/DigiSchol/Digital Research and Curator Team/Projects & Proposals/00_Current Projects"
#     "/LibCrowds Convert-a-Card (Adi)/OCR/20230504 TKB Export P5 175 GT pp/1016992/P5_for_Transkribus"
# )

idx = int(option.split(" ")[0])
card_jpg_path = os.path.join("data/images", to_show.loc[idx, "xml"][:-4] + ".jpg")

st.image(Image.open(card_jpg_path))

st.markdown("## Select from worldcat results")

c1, c2, c3 = st.columns(3)
res_to_pick = [0,1,2]

with c1:
    res = to_show.loc[idx, "worldcat_result"][res_to_pick[0]].get_fields()
    st.dataframe(pd.DataFrame(index=[int(x.tag) for x in res], data=[x.text() for x in res], columns=[res_to_pick[0]]))

with c2:
    res = to_show.loc[idx, "worldcat_result"][res_to_pick[1]].get_fields()
    st.dataframe(pd.DataFrame(index=[int(x.tag) for x in res], data=[x.text() for x in res], columns=[res_to_pick[1]]))

with c3:
    res = to_show.loc[idx, "worldcat_result"][res_to_pick[2]].get_fields()
    st.dataframe(pd.DataFrame(index=[int(x.tag) for x in res], data=[x.text() for x in res], columns=[res_to_pick[2]]))

good_res = st.radio(
    "Which is the correct Worldcat result?",
    (*res_to_pick, "None of the results are correct")
)