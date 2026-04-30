#!/bin/bash
python server.py &
streamlit run parent_dashboard.py \
  --server.port=8080 \
  --server.address=0.0.0.0 \
  --server.headless=true
