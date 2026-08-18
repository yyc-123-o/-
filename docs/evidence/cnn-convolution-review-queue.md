# CNN Convolution Evidence Review Queue

This handoff is the result of the deterministic review-queue command:

```powershell
uv run python scripts/build_cnn_evidence_review_queue.py `
  --input-file 'D:\张维揭榜挂帅\知识库\processed\chunks\ai_learning_pilot_review_300.jsonl' `
  --output-file reports/generated/cnn-evidence-review/cnn_evidence_review_queue.json
```

The queue is candidate-only. It does not modify
`resources/evidence/evidence_manifest_v1.yaml`, and it cannot open the strict
resource-generation gate by itself.

## Audit Result

| Field | Result |
|---|---|
| Concept | `dl.cnn.convolution` |
| Depth | `intro` |
| Candidate rows | 21 |
| Definition rows | 13 |
| Code rows | 8 |
| Exercise rows | 0 |
| Excluded rows | 279 |
| Publishable | `false` |
| Review status | `candidate` |

The accepted rows all come from `dl_ch09_cnn`, titled **DeepLearning Chapter 9
Convolutional Networks**, with source URL
`https://github.com/MingchaoZhu/DeepLearning`, MIT license metadata, and S2
tier metadata. The queue still requires human review; `license_status=allowed`
in the intake snapshot is not equivalent to a published evidence decision.

## Recommended Definition Candidate

Start review with `dl_ch09_cnn_a3dde521400f`, locator `page 1`. It contains the
definition of convolution, the filter/kernel interpretation, the input/output
feature-map terminology, and a two-dimensional cross-correlation example.

Additional definition candidates cover channels, padding, stride, output-size
formulas, and parameter counts. They should be reviewed for overlap before
creating duplicate formal records.

## Code Gap

The eight accepted code rows are custom NumPy/`Conv2D` implementations. They
are useful candidate context, but none contains the required PyTorch
`nn.Conv2d` example. The queue therefore reports:

```json
[
  "pytorch_nn_conv2d",
  "exercise"
]
```

Do not promote a custom `Conv2D` implementation as the requested PyTorch code
evidence. A separate authorized PyTorch source or a project-authored code
example must be reviewed before publication.

## Exercise Gap

No CNN exercise row was found in the teammate snapshot for this concept. The
formal resource blueprint requires an exercise covering output-size
calculation, convolution-kernel parameter count, and padding/stride effects,
with answer and explanation. This material must be sourced or authored and
then reviewed; it cannot be inferred from a definition or code row.

## Exclusion Audit

The queue excludes:

- 255 rows whose concept labels do not match `dl.cnn.convolution`;
- 18 rows whose titles/sections do not identify CNN/convolution, despite a
  likely erroneous concept binding;
- 4 rows with unsupported content kinds;
- 2 rows from disallowed source families.

The disallowed-family rule covers GAN/DCGAN, TextCNN, diffusion, transposed
convolution, and related source text. These rows must not satisfy standard
convolution evidence requirements.

## Human Review Checklist

Before adding any record to the formal evidence manifest, a reviewer must:

1. Verify the canonical source URL, exact source version/commit, MIT license,
   locator, and whether redistribution of the excerpt is allowed.
2. Confirm that the excerpt teaches standard convolution rather than GAN,
   TextCNN, diffusion, transposed convolution, or an unrelated method.
3. Confirm the exact concept, `intro` depth, language, content kind, and
   normalized content hash.
4. Supply a real reviewer identity and review timestamp.
5. Add all three required content kinds only after definition, PyTorch code,
   and exercise coverage are present.
6. Run the manifest validator and the strict three-Agent integration test.

Until these checks are complete, strict mode must remain blocked and candidate
preview must remain explicitly non-publishable.
