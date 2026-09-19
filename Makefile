install:
	python -m pip install -e .

test:
	python -m pytest -q

discover:
	wq-evoforge discover

once:
	wq-evoforge once

run:
	wq-evoforge run
