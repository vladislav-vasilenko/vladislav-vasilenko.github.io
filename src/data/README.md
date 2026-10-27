# Intro molecular geometry

`intro-molecules.json` is a small, bundled coordinate snapshot, prepared on 2026-10-28. Rendering requires no external chemistry API.

| Molecule | Coordinate source | Heavy atoms | Bonds |
| --- | --- | ---: | ---: |
| Dopamine, C8H11NO2 | [PubChem CID 681](https://pubchem.ncbi.nlm.nih.gov/compound/681), computed 3D conformer | 11 | 11 |
| Serotonin, C10H12N2O | [PubChem CID 5202](https://pubchem.ncbi.nlm.nih.gov/compound/5202), computed 3D conformer | 13 | 14 |
| Adrenaline, C9H13NO3 | [PubChem CID 5816](https://pubchem.ncbi.nlm.nih.gov/compound/5816), computed 3D conformer | 13 | 13 |
| Oxytocin, C43H66N12O12S2 | [RCSB PDB 7RYC](https://www.rcsb.org/structure/7RYC), observed receptor-bound peptide, author chain L | 69 | 71 |

PubChem downloads use `/rest/pug/compound/cid/{cid}/JSON?record_type=3d`; each molecule stores its exact coordinate-source URL. Hydrogen atoms are removed from the rendered graph, not from the molecular formula. PubChem bond orders are retained. Oxytocin has no available PubChem 3D conformer in this snapshot, so its geometry comes from [7RYC.pdb](https://files.rcsb.org/download/7RYC.pdb), including the terminal NH2 group. Its Cys1–Cys6 disulfide connection is explicit in that PDB. Other peptide covalent bonds were assigned using element covalent radii plus a 0.3 Å tolerance; carbonyl double bonds use C–O lengths below 1.29 Å, with alternating Tyr aromatic bonds. Tests validate composition, connectivity, bond lengths, cycle counts and the sulfur bridge.

The coordinates are centered and rigidly aligned with their principal axes in a right-handed frame, then rounded to four decimals. Distances remain in angstroms before visual fitting. The animation uses one conformation, with stylized rotation/breathing and cube-based atoms/bonds. It is neither a molecular-dynamics simulation nor a depiction of chemical conversion between these compounds.

The pop-culture captions (“pleasure molecule”, “happiness hormone”, “love molecule”) are labeled as associations, rather than complete physiological descriptions.
