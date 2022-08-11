import os
import shutil
import json
from pathlib import Path

import random
import functools
from IPython.display import display, clear_output
from ipywidgets import Button, Dropdown, HTML, HBox, IntSlider, FloatSlider, Textarea, Output


def load_data(path):

    annotations_path = path + 'metadata_for_annotations.json'
    print(annotations_path)
    
    # First time annotating: create your own annotation file:
    if not Path(annotations_path).exists():
        os.makedirs(os.path.dirname(annotations_path), exist_ok=True)
        shutil.copyfile(path + 'metadata_for_annotations.json', annotations_path)

    # Load annotation file:
    data_to_annotate = dict()
    with open(annotations_path) as f:
        data_to_annotate = json.load(f)

    return data_to_annotate


# Store annotations as a json file:
def store_annotations(path, name, annotations, data_to_annotate):

    annotations_path = path +  "annotations.json"

    for x in annotations:
        data_to_annotate[x] = annotations[x]
    json.dump(data_to_annotate, open(annotations_path, 'w'))


# Annotation function. Code adapted from: https://github.com/agermanidis/pigeon/blob/master/pigeon/annotate.py
def annotate():

    path ="cards_txt/"

    data_to_annotate = load_data(path)

    # examples: list(any), list of items to annotate
    examples = [r for r in data_to_annotate if data_to_annotate[r] == ""]

    """
    Build an interactive widget for annotating a list of input examples.
    """
    examples = list(examples)

    annotations = dict()
    current_index = -1

    total_examples = len(data_to_annotate)
    done_previously = 0
    for k in data_to_annotate:
        if data_to_annotate[k]:
            done_previously += 1

    def set_label_text():
        nonlocal count_label
        count_label.value = '{} examples annotated out of {}'.format(
            done_previously + len(annotations), len(data_to_annotate)
        )

    def show_next():
        nonlocal current_index
        current_index += 1
        set_label_text()
        if current_index >= len(examples):
            for btn in buttons:
                btn.disabled = True
            print('Annotation done.')
            return
        if current_index <= 0:
            buttons[2].disabled = True
        elif current_index > 0:
            buttons[2].disabled = False
        with out:
            clear_output(wait=True)
            print(examples[current_index])

    def show_previous():
        nonlocal current_index
        current_index -= 1
        set_label_text()
        if current_index <= 0:
            buttons[2].disabled = True
        elif current_index > 0:
            buttons[2].disabled = False
        with out:
            clear_output(wait=True)
            print(examples[current_index])

    def add_annotation(annotation):
        annotation = annotation.strip()
        if annotation != "":
            if (annotation[0].lower() == "q" and annotation[1:].isnumeric()) or (annotation == "not in WorldCat"):
                annotations[examples[current_index]] = annotation
                store_annotations(path, name, annotations, data_to_annotate)
                show_next()

    def skip(btn):
        show_next()

    def no_match(btn):
        add_annotation("not in WorldCat")

    def back(btn):
        show_previous()

    count_label = HTML()
    set_label_text()
    display(count_label)

    buttons = []
    
    ta = Textarea()
    display(ta)
    btn = Button(description='submit')
    def on_click(btn):
        add_annotation(ta.value)
    btn.on_click(on_click)
    buttons.append(btn)

    btn = Button(description='not in WorldCat')
    btn.on_click(no_match)
    buttons.append(btn)

    btn = Button(description='back')
    btn.on_click(back)
    buttons.append(btn)

    btn = Button(description='skip')
    btn.on_click(skip)
    buttons.append(btn)

    box = HBox(buttons)
    display(box)

    out = Output()
    display(out)

    
    show_next()

import glob
for f in glob.glob('cards_txt/*.txt'):
    with open(f, 'r') as text:
        textfile = text.read()
        print(textfile)
    annotate()

# # Load data:
# def load_data():
#     name = os.getcwd().split("/")[2].split("jupyter-")[1]
#     path ="/srv/data/bho_wikidata/"+name+"/"
#     annotations_path = path+ name + "_" + 'annotations.json'

#     # First time annotating: create your own annotation file:
#     if not Path(annotations_path).exists():
#         os.makedirs(os.path.dirname(path), exist_ok=True)
#         shutil.copyfile('/srv/data/bho_wikidata/samples_to_annotate.json', annotations_path)

#     # Load annotation file:
#     data_to_annotate = dict()
#     with open(annotations_path) as f:
#         data_to_annotate = json.load(f)

#     return data_to_annotate
