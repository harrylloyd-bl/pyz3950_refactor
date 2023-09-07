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
import s3fs


st.markdown("# Worldcat results for searches for catalogue card title/author")

s3 = s3fs.S3FileSystem(anon=False)


@st.cache_data
def load_s3(s3_path):
    with s3.open(s3_path, 'rb') as f:
        df = pickle.load(f)
        # st.write("Cards data loaded from S3")
    return df


cards_df = load_s3('cac-bucket/cards_df.p')
# cards_df = pickle.load(open("notebooks/cards_df.p", "rb"))
nulls = len(cards_df) - len(cards_df.dropna(subset="worldcat_matches"))
errors = len(cards_df.query("worldcat_matches == 'Error'"))
cards_to_show = cards_df.query("worldcat_matches != 'Error'").dropna(subset="worldcat_matches")
cards_to_show.insert(loc=0, column="card_id", value=range(1, len(cards_to_show) + 1))

st.write(f"Showing {len(cards_to_show)} cards with Worldcat results out of of {len(cards_df)} total cards, "
         f"omitting {nulls} without results and {errors} with errors in result retrieval")
subset = ("card_id", "title", "author", "selected_match", "match_needs_editing", "shelfmark", "worldcat_matches", "lines")

select_c1, select_c2 = st.columns([0.4, 0.6])
selected_card = select_c1.number_input(
    "Select a card to match",
    min_value=1, max_value=len(cards_to_show),
    help="Type or use +/-"
)

to_show_df_display = st.empty()
to_show_df_display.dataframe(cards_to_show.loc[:, subset], hide_index=True)#.set_index("card_id", drop=True))
cards_to_show["author"][cards_to_show["author"].isna()] = ""  # handle None values

# option_dropdown = st.selectbox(
#     "Which result set do you want to choose between?",
#     pd.Series(cards_to_show.index, index=cards_to_show.index, dtype=str)
#     + " ti: " + cards_to_show["title"] + " au: " + cards_to_show["author"]
# )
# card_idx = int(option.split(" ")[0])
readable_idx = int(selected_card)
card_idx = cards_to_show.query("card_id == @readable_idx").index.values[0]
# card_idx = int(option)

if cards_to_show.loc[card_idx, "selected_match"]:
    select_c2.markdown(":green[**This record has already been matched!**]")

st.write("\n")
st.markdown("#### Select from Worldcat results")


# p5_root = (
#     "G:/DigiSchol/Digital Research and Curator Team/Projects & Proposals/00_Current Projects"
#     "/LibCrowds Convert-a-Card (Adi)/OCR/20230504 TKB Export P5 175 GT pp/1016992/P5_for_Transkribus"
# )

card_jpg_path = os.path.join("data/images", cards_to_show.loc[card_idx, "xml"][:-4] + ".jpg")


ic_left, ic_centred, ic_right = st.columns([0.2,0.6,0.2])
ic_centred.image(Image.open(card_jpg_path), use_column_width=True)
label_text = """
**Right**:  
Catalogue card\n
**Below**:  
OCLC MARC match table\n
Filters and sort options are below the table
"""
ic_left.write(label_text)

marc_table = st.empty()
search_ti = cards_to_show.loc[card_idx, 'title'].replace(' ', '+')
search_au = cards_to_show.loc[card_idx, 'author'].replace(' ', '+')
search_term = f"https://www.worldcat.org/search?q=ti%3A{search_ti}+AND+au%3A{search_au}"
st.markdown(f"You can also check the [Worldcat search]({search_term}) for this card")
match_df = pd.DataFrame({"record": list(cards_to_show.loc[card_idx, "worldcat_matches"].values())})

# filter options
match_df["has_title"] = match_df["record"].apply(lambda x: bool(x.get_fields("245")))
match_df["has_author"] = match_df["record"].apply(lambda x: bool(x.get_fields("100", "110", "111", "130")))
au_exists = bool(search_au)
match_df = match_df.query("has_title == True and (has_author == True or not @au_exists)")

lang_xml = requests.get("https://www.loc.gov/standards/codelists/languages.xml")
tree = ET.fromstring(lang_xml.text)
lang_dict = {lang[2].text: lang[1].text for lang in tree[4]}

re_040b = re.compile(r"\$b[a-z]+\$")
match_df["language_040$b"] = match_df["record"].apply(lambda x: re_040b.search(x.get_fields("040")[0].__str__()).group())
match_df["language"] = match_df["language_040$b"].str[2:-1].map(lang_dict)

lang_select = st.multiselect(
    "Select Cataloguing Language (040 $b)",
    match_df["language"].unique(),
    format_func=lambda x: f"{x} ({len(match_df.query('language == @x'))} total)"
)

if not lang_select:
    filtered_df = match_df
else:
    filtered_df = match_df.query("language in @lang_select").copy()

# sort options
subject_access = [
    "600", "610", "611", "630", "647", "648", "650", "651",
    "653", "654", "655", "656", "657", "658", "662", "688"
]

filtered_df["num_subject_access"] = filtered_df["record"].apply(lambda x: len(x.get_fields(*subject_access)))
filtered_df["num_linked"] = filtered_df["record"].apply(lambda x: len(x.get_fields("880")))
filtered_df["has_phys_desc"] = filtered_df["record"].apply(lambda x: bool(x.get_fields("300")))
filtered_df["good_encoding_level"] = filtered_df["record"].apply(lambda x: x.get_fields("LDR")[0][17] not in [3, 5, 7])
filtered_df["record_length"] = filtered_df["record"].apply(lambda x: len(x.get_fields()))

input_max = st.number_input("Max records to display", min_value=1, value=3)
if input_max <= len(filtered_df):
    max_to_display = int(input_max)
else:
    max_to_display = len(filtered_df)


def pretty_filter_option(option):
    display_dict = {
        "num_subject_access": "Number of subject access fields",
        "num_linked": "Number of linked fields",
        "has_phys_desc": "Has a physical description",
        "good_encoding_level": "Encoding level not 3/5/7",
        "record_length": "Number of fields in record"
    }
    return display_dict[option]


sort_options = st.multiselect(
    label=(
        "Select how to sort matching records. The default is the order the results are returned from Worldcat."
        " Results will be sorted in the order options are selected"
    ),
    options=["num_subject_access", "num_linked", "has_phys_desc", "good_encoding_level", "record_length"],
    format_func=pretty_filter_option
)


def gen_unique_idx(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a unique index from one that contains repeated fields
    @param df: pd.DataFrame
    @return: pd.DataFrame
    """
    df["Repeat Field ID"] = ""
    dup_idx = df.index[df.index.duplicated()].unique()
    unhandled_fields = [x for x in dup_idx if x not in ["650", "880"]]
    if "650" in dup_idx:
        str_add = df.loc["650", df.columns[0]].copy()
        str_add = [" " + str(x) for x in range(len(str_add))]
        df.loc["650", "Repeat Field ID"] = df.loc["650", df.columns[0]].str.split(" ").transform(lambda x: x[0]) + str_add
    if "880" in dup_idx:
        str_add = df.loc["880", df.columns[0]].copy()
        str_add = [" " + str(x) for x in range(len(str_add))]
        df.loc["880", "Repeat Field ID"] = df.loc["880", df.columns[0]].str.split("/").transform(lambda x: x[0]) + str_add
    for dup in unhandled_fields:
        df.loc[dup, "Repeat Field ID"] = [str(x) for x in range(len(df.loc[dup]))]

    return df.set_index("Repeat Field ID", append=True)


def sort_fields_idx(index: pd.Index) -> pd.Index:
    """
    Specific keys to sort indices containing MARC fields
    @param index: pd.Index
    @return: pd.Index
    """
    if index.name == "MARC Field":
        key = [0 if x == "LDR" else int(x) for x in index]
        return pd.Index(key)
    elif index.name == "Repeat Field ID":
        key = [x.split("$")[1] if "$" in x else x for x in index]
        return pd.Index(key)


matches_to_show = filtered_df.sort_values(
    by=sort_options,
    ascending=False
)

displayed_matches = []
for i in range(len(matches_to_show)):
    res = matches_to_show.iloc[i, 0].get_fields()
    ldr = matches_to_show.iloc[i, 0].get_fields("LDR")
    col = pd.DataFrame(
        index=pd.Index(["LDR"] + [x.tag for x in res], name="MARC Field"),
        data=ldr + [x.__str__()[6:] for x in res],
        columns=[matches_to_show.iloc[i].name]
    )
    displayed_matches.append(gen_unique_idx(col))

st_display_df = pd.concat(displayed_matches, axis=1).sort_index(key=sort_fields_idx)
match_ids = st_display_df.columns.tolist()
records_to_ignore = st.multiselect(
    label="Select any bad records you'd like to remove from the comparison",
    options=match_ids
)

records_to_display = [x for x in match_ids if x not in records_to_ignore]
marc_table.dataframe(st_display_df.loc[:, records_to_display[:max_to_display]])

# cols = st.columns(max_to_display)
#
# for i, c in enumerate(cols):
#     with c:
#         res = matches_to_show.iloc[i-1, 0].get_fields()
#         st.dataframe(pd.DataFrame(
#             index=[int(x.tag) for x in res],
#             data=[x.__str__()[6:] for x in res],
#             columns=[i]))
col1, col2, col3 = st.columns(3)
best_res = col1.radio(
    label="Which is the closest Worldcat result?",
    options=(records_to_display[:max_to_display] + ["None of the results are correct"])
)
needs_editing = col2.radio(
    label="Does this record need manual editing or is it ready to ingest?",
    options=[True, False],
    format_func=lambda x: {True: "Manual editing", False: "Ready to ingest"}[x]
)
save_res = col3.button(
    label="Save selection"
)
clear_res = col3.button(
    label="Clear selection"
)


def assign_dict(row, idx, matching_record):
    if row.name == idx:
        return {matching_record: row["worldcat_matches"][matching_record]}
    else:
        return row["selected_match"]


if save_res:
    # Arrow doesn't like the PyMARC Record type, so need to keep it in a dict
    # but can't assign dict to df loc so assign_dict is a workaround
    if best_res == "None of the results are correct":
        cards_df.loc[card_idx, "selected_match"] = "No matches"
    else:
        assign_selection = cards_df.apply(assign_dict, idx=card_idx, matching_record=best_res, axis=1)
        cards_df["selected_match"] = assign_selection
        cards_df.loc[card_idx, "match_needs_editing"] = needs_editing

    with s3.open('cac-bucket/cards_df.p', 'wb') as f:
        pickle.dump(cards_df, f)
    st.cache_data.clear()

    nulls = len(cards_df) - len(cards_df.dropna(subset="worldcat_matches"))
    errors = len(cards_df.query("worldcat_matches == 'Error'"))
    cards_to_show = cards_df.query("worldcat_matches != 'Error'").dropna(subset="worldcat_matches")
    cards_to_show.insert(loc=0, column="card_id", value=range(1, len(cards_to_show) + 1))
    to_show_df_display.dataframe(cards_to_show.loc[:, subset], hide_index=True)  # subset defined line 34

    st.markdown("### Selection saved!")

if clear_res:
    cards_df.loc[card_idx, "selected_match"] = None
    cards_df.loc[card_idx, "match_needs_editing"] = None
    with s3.open('cac-bucket/cards_df.p', 'wb') as f:
        pickle.dump(cards_df, f)
    st.cache_data.clear()

    nulls = len(cards_df) - len(cards_df.dropna(subset="worldcat_matches"))
    errors = len(cards_df.query("worldcat_matches == 'Error'"))
    cards_to_show = cards_df.query("worldcat_matches != 'Error'").dropna(subset="worldcat_matches")
    cards_to_show.insert(loc=0, column="card_id", value=range(1, len(cards_to_show) + 1))
    to_show_df_display.dataframe(cards_to_show.loc[:, subset], hide_index=True)  # subset defined line 34

    st.markdown("### Selection cleared!")
