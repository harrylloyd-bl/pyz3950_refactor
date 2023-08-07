This repo is part of the Convert-a-Card project to convert catalogue cards, primarily from the Asian and African Studies Reading Room at the BL.
Code here consumes xml files produced from card transcription by [Transkribus](lite.transkribus.eu),
parses the xml to extract card title/author/shelfmark the queries [OCLC Worldcat](https://www.worldcat.org/) to see if a matching record exists.

The prototype for this repo was created by Giorgia Tolfo and Victoria Morris and has been developed to working stage by
Harry LLoyd. Readme by HL.

Structure  
```
├── README.md           <- The top-level README for developers using this project.  
├── data  
│   ├── processed       <- The final, canonical data sets  
│   └── raw             <- The original, immutable data dump.  
│  
├── notebooks           <- Jupyter notebooks.  
│  
├── reports             <- Generated analysis as HTML, PDF, LaTeX, etc.  
│   └── figures         <- Generated graphics and figures to be used in reporting  
│  
├── hide_env.txt        <- hidden conda/mamba environment to force streamlit recreate from requirements.txt, recreated via e.g. conda create -f environment.yml
├── requirements.txt	<- pip freeze environment solely for streamlit use
│  
├── src                 <- Source code for use in this project.  
│   ├── __init__.py     <- Makes src a Python module  
│   │  
│   ├── data            <- Scripts to download or generate data  
│   │   └── oclc.py     <- wrappers for Zoom queries to query OCLC Worldcat
│   │   └── xml_extraction.py   <- extract labelled text from xml files 
│
├── tests               <- pytest unit tests for src  
│
└── z3950               <- combined PyZ3950 and PyMARC modules to run Z3950 queries and display MARC records
```