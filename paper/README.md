# COINS paper

[`main.tex`](main.tex) is the paper source, and [`main.pdf`](main.pdf) is the paper PDF. Chapters are in `chapters/`, and figures are in `images/`.

## Build

From this directory, with a TeX installation containing the packages used by the source:

```sh
mkdir -p _build
pdflatex -jobname=main -interaction=nonstopmode -halt-on-error -output-directory=_build main.tex
(cd _build && BIBINPUTS=..: BSTINPUTS=..: bibtex main)
pdflatex -jobname=main -interaction=nonstopmode -halt-on-error -output-directory=_build main.tex
pdflatex -jobname=main -interaction=nonstopmode -halt-on-error -output-directory=_build main.tex
```

The output is `_build/main.pdf`. `example_paper.bib` supplies the bibliography.
