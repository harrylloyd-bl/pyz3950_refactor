This repo created by Giorgia Tolfo and picked up by Harry LLoyd, readme by HL.

This repo is part of the Convert-a-Card project to convert catalogue cards, primarily from the Asian and African Studies Reading Room at the BL.
Code here consumes xml files produced from card transcription by [Transkribus] (lite.transkribus.eu), parses the xml to extract card title/author/shelfmark the queries [OCLC Worldcat] (https://www.worldcat.org/) to see if a matching record exists.

Structure  
├── README.md          <- The top-level README for developers using this project.  
├── data  
│   ├── processed      <- The final, canonical data sets  
│   └── raw            <- The original, immutable data dump.  
│  
├── notebooks          <- Jupyter notebooks. Naming convention is a number (for ordering),  
│                         the creator's initials, and a short `-` delimited description, e.g.  
│                         `1.0-jqp-initial-data-exploration`.  
│  
├── reports            <- Generated analysis as HTML, PDF, LaTeX, etc.  
│   └── figures        <- Generated graphics and figures to be used in reporting  
│  
├── environment.yml	<- conda/mamba environment, recreated via e.g. conda create -f environment.yml  
│  
├── src                <- Source code for use in this project.  
│   ├── __init__.py    <- Makes src a Python module  
│   │  
│   ├── data           <- Scripts to download or generate data  
│   │   └── make_dataset.py  
│   │  
│   ├── features       <- Scripts to turn raw data into features for modeling  
│   │   └── build_features.py  
│   │  
│   ├── models         <- Scripts to train models and then use trained models to make  
│   │   │                 predictions  
│   │   ├── predict_model.py  
│   │   └── train_model.py  
│   │  
│   └── visualization  <- Scripts to create exploratory and results oriented visualizations  
│       └── visualize.py  
