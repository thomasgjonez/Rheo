.PHONY: setup graph api web build serve test

PBF_URL := https://download.bbbike.org/osm/bbbike/SanFrancisco/SanFrancisco.osm.pbf

setup:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements.txt
	npm --prefix frontend install

data/raw/SanFrancisco.osm.pbf:
	mkdir -p data/raw
	curl -L -o $@ $(PBF_URL)

data/sf_graph.npz: data/raw/SanFrancisco.osm.pbf backend/scripts/build_graph.py
	cd backend && .venv/bin/python scripts/build_graph.py ../data/raw/SanFrancisco.osm.pbf ../data/sf_graph.npz

graph: data/sf_graph.npz

# Two terminals: `make api` and `make web`, then open http://localhost:5173
api: graph
	cd backend && .venv/bin/uvicorn rheo.api:app --reload --port 8000

web:
	npm --prefix frontend run dev

build:
	npm --prefix frontend run build

# One process: builds the frontend and serves everything at http://localhost:8000
serve: graph build
	cd backend && .venv/bin/uvicorn rheo.api:app --port 8000

test:
	cd backend && .venv/bin/python -m pytest -q
	npm --prefix frontend run build
