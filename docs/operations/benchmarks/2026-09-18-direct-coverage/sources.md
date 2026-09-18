# Research adoption and source boundary

The external research report is identified by SHA-256 in `plan.json`. Its useful
hypothesis is to separate candidate eligibility, direct content evidence, quality,
and final keeper selection. Its historical citations and claims are not imported
as acceptance evidence. This experiment implements one bounded baseline; neither
a direct witness nor a homography establishes semantic coverage by itself.

## Adopted implementation

[OpenCV 4.13.0 feature matching and homography tutorial](https://docs.opencv.org/4.13.0/d1/de0/tutorial_py_feature_homography.html)
documents SIFT matching, ratio filtering and RANSAC inlier masks. We use CPU SIFT,
a spatial-support check, target overlap, robust brightness alignment and local
gray residuals. This extends geometric correspondence into an **experimental**
coverage predicate; that extension is our hypothesis, not an OpenCV guarantee.

Runtime: `opencv-python==4.13.0.92`, OpenCV `4.13.0`; no downloaded model weights.
The upstream 4.13.0 tag resolves to
`fe38fc608f6acb8b68953438a62305d8318f4fcd`; its
[LICENSE](https://github.com/opencv/opencv/blob/fe38fc608f6acb8b68953438a62305d8318f4fcd/LICENSE)
is Apache-2.0. The installed Python wrapper has its own MIT notice and bundled
third-party notices. This experiment does not strip or replace those notices.
LightGlue/DINO or other learned weights are not adopted, so no downstream license
claim is inferred for them.

## Data

- [HDR+ dataset](https://www.hdrplusdata.org/dataset.html): Hasinoff et al.,
  *Burst photography for high dynamic range and low-light imaging on mobile
  cameras*, ACM TOG 2016. Provider links CC-BY-SA 4.0. Two lexicographically first
  eligible events after excluding the prior 22 events were selected before
  viewing, first three payloads each, with a 200 MB download cap. Immutable source
  URLs/digests are in `inputs.json`. No image redistribution occurs in Git.
  Two independent Codex panels used opposite order and allowed tie/unknown;
  `blind-references.json` is model-generated evidence, not human ground truth.
- [MPII Cooking 2](https://www.mpi-inf.mpg.de/departments/computer-vision-and-machine-learning/research/human-activity-recognition/mpii-cooking-2-dataset/):
  Rohrbach et al., *Recognizing Fine-Grained and Composite Activities using
  Hand-Centric Features and Script Data*, IJCV 2015. Previously selected scientific
  diagnostic videos/annotations are reused locally; provider terms limit use to
  scientific purposes and prohibit redistribution. This is not a commercial
  deployment or model-training permission claim, and organizational use is not
  assumed to be personal use. Official disjoint action labels are negative
  proxies; equal labels never prove duplicate content.
- [UCSD SIG17HDR](https://cseweb.ucsd.edu/~viscomp/projects/SIG17HDR/): the existing
  three-file real exposure bracket is reused read-only. The inspected material
  did not establish redistribution permission; no source assets are committed.
  Subject pose can change, so common scene identity is not positive coverage truth.
- Synthetic perturbations use seeded procedural texture, not image assets. Small
  patches are symbolic content controls, not realistic face/expression or action
  ground truth. Noise/shadow controls have construction-based content identity;
  foliage/water/parallax/occlusion controls deliberately allow unknown.

No production database, review session, cloud VLM, photo writer or XMP writer is
constructed by the benchmark. Decoded previews exist in memory only. Reports
contain identifiers, fingerprints and measurements; source hashes are checked
before and after evaluation. Public photo/video bytes stay outside Git.
