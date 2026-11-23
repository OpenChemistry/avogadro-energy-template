# avogadro-energy-template

A [copier](https://copier.readthedocs.io/) template for Avogadro 2 **energy
models** — the plugins that appear in the force field list and answer energy,
gradient and Hessian requests during optimization and dynamics.

For menu commands, the far more common plugin type, use
[avogadro-command-template](https://github.com/openchemistry/avogadro-command-template) instead. 
If you're interested in electrostatic models, file formats, and [input generators](https://github.com/openchemistry/avogenerators)
please ask on the [Avogadro forum](https://discuss.avogadro.cc/)

## Usage

```bash
pixi global install copier     # or: uv tool install copier
copier copy gh:openchemistry/avogadro-energy-template avogadro-myff
# you'll be asked some questions like the name of your plugin and dependencies
cd avogadro-myff
# edit your code as needed, e.g. src/{{module name}}/*.py
pixi install
pixi run test
# now you can use "Install from Directory..." in the Manage Plugins dialog
# to test out 
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
├── .github/               daily check for new PyPI / conda-forge releases
├── src/avogadro_myff/
│   ├── __init__.py         argparse + match/case, optional setup()
│   ├── myff.py             the model, then the protocol loop
│   ├── charges.py          optional electrostatic model - remove it if you don't assign charges
│   └── customization/
│       └── myff_options.json   optional user-options dialog (e.g., solvent)
├── scripts/
│   └── check_in_avogadro.py   checks the models in a real Avogadro, over RPC
└── tests/
    ├── conftest.py         a client for the binary protocol
    ├── data/water.json     a real Avogadro bootstrap JSON
    └── test_energy.py
```

The tests drive the real energy protocol against the real entry point, so they
catch what actually breaks energy plugins: a gradient returned with the sign of
a force, an energy left in eV or Hartree, and anything writing to stdout, which
is the protocol.

`scripts/check_in_avogadro.py` is the other half: it launches a real Avogadro
(`--app`) once per model in the plugin's `pyproject.toml` and checks, over
JSON-RPC, that the model is offered, that the first (cold) and second energy
are finite, that an optimization lowers the energy, and that the `support.unit-cell`
and `support.ions` promises hold for a crystal and an anion. It needs Python
3.11+ and nothing else, and the plugin installed in that Avogadro. A released
Avogadro may not wait long enough for a model that is slow to start; the
script says so when the first call fails.

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

## Dependency updates

The `track_dependencies` question lists packages to watch, and becomes
`[tool.update-dependencies]` in `pyproject.toml`. Once the plugin is on GitHub,
`.github/workflows/update-dependencies.yml` checks daily for new releases:
PyPI for packages in `[project].dependencies` or
`[tool.pixi.pypi-dependencies]`, conda-forge for `[tool.pixi.dependencies]`. A
conda-forge release only counts once it is built for every platform the plugin
lists, because pixi solves all of them. When a tracked package has a new
release, the workflow opens a pull request that raises that package's `>=`
floor and bumps the patch version in `[project].version`. Merge it, and
the Avogadro plugin index picks up the new commit; installed copies then show
"Update available", and updating reinstalls the plugin with the new release.

For the workflow to open pull requests, enable *Settings → Actions → General →
Allow GitHub Actions to create and approve pull requests* in the repository.
If `pixi.lock` is committed, the workflow also runs `pixi lock` and includes
the refreshed lockfile in the pull request.

## Licenses

The `license` question offers BSD-3-Clause and MIT, and writes the full text.
For anything else, pick either one, then replace `LICENSE` and change the
`license` field in `pyproject.toml` to the right SPDX identifier.

## Reference

- [Writing plugins](https://avogadro.cc/develop/plugins/)
- [Input and output JSON](https://avogadro.cc/develop/plugins/io.html)
- `avogadro/qtplugins/forcefield/scriptenergy.cpp` in avogadrolibs — the C++
  side of everything above
