# avogadro-energy-template

A [copier](https://copier.readthedocs.io/) template for Avogadro 2 **energy
models** — the plugins that appear in the force field list and answer energy,
gradient and Hessian requests during optimization and dynamics.

For menu commands, the far more common plugin shape, use
[avogadro-plugin-template](../avogadro-plugin-template) instead. File formats
and input generators are not covered by either; see
[avo-plugin-demo](https://github.com/OpenChemistry/avo-plugin-demo).

## Usage

```bash
pixi global install copier     # or: uv tool install copier
copier copy /path/to/avogadro-energy-template avogadro-myff
cd avogadro-myff
pixi install
pixi run test
```

To pull in later improvements to this template:

```bash
copier update
```

(`copier update` requires the generated project to be a git repository with the
`.copier-answers.yml` file committed.)

## What you get

```
avogadro-myff/
├── pyproject.toml          [project] + [tool.pixi.*] + [tool.avogadro]
├── README.md
├── LICENSE
├── .gitignore
├── .gitattributes          pixi.lock as a binary-merge, generated file
├── src/avogadro_myff/
│   ├── __init__.py         argparse + match/case, optional setup()
│   ├── myff.py             the model, then the protocol loop
│   ├── charges.py          optional electrostatic model
│   └── customization/
│       └── myff_options.json   optional user-options dialog
└── tests/
    ├── conftest.py         a client for the binary protocol
    ├── data/water.json     a real Avogadro bootstrap JSON
    └── test_energy.py
```

The generated plugin runs as soon as it is created, either on a built-in
Lennard-Jones potential with no dependencies, or on an
[ASE](https://wiki.fysik.dtu.dk/ase/) calculator — the shape used by
`avogadro-mace`, `avogadro-mattersim` and friends, including the periodic-image
handling that a unit cell needs. Either way the protocol plumbing is already
correct, and only the marked calculation functions need replacing.

## The binary protocol

Energy models are long-running: Avogadro starts one process, writes a line of
bootstrap JSON, and then exchanges framed binary messages with it until the
model is deselected. The template declares `protocol = "binary-v1"` and builds
on `avogadro.energy`, which ships in the
[`avogadro` wheel](https://pypi.org/project/avogadro/) and is added as a
dependency of every generated project. There is no copy of the protocol code to
keep in sync.

The alternative is the older line-based text protocol, used by
`avogadro-ob-energy`. It is simpler to read but cannot carry batches or
Hessians, and it is not generated here.

## Notes on the generated metadata

- The `[project.scripts]` entry point **must** begin with `avogadro-`;
  Avogadro's package manager scans for exactly that prefix.
- The `support.*` keys are enforced, not advisory. Avogadro refuses to run a
  model on a molecule outside them — a charged molecule with
  `support.ions = false`, or a crystal with `support.unit-cell = false` — so
  they have to match what the code really handles.
- `support.batch` and `support.hessians` gate the corresponding requests. A
  model that implements batching without declaring it, as `avogadro-aimnet2`
  currently does, simply never receives a batch.
- Avogadro reads `protocol` by prefix, so `"binary"` and `"binary-v1"` both
  select the binary path. The template writes `"binary-v1"`.
- `user-options` is a filesystem path relative to the plugin directory, so the
  options JSON can live anywhere; this template keeps it inside the package so
  it also ships in a built wheel.

## Licenses

The `license` question offers BSD-3-Clause and MIT, and writes the full text.
For anything else, pick either one, then replace `LICENSE` and change the
`license` field in `pyproject.toml` to the right SPDX identifier.

## Reference

- [Writing plugins](https://two.avogadro.cc/develop/plugins/)
- [Input and output JSON](https://two.avogadro.cc/develop/plugins/io.html)
- `avogadro/qtplugins/forcefield/scriptenergy.cpp` in avogadrolibs — the C++
  side of everything above
