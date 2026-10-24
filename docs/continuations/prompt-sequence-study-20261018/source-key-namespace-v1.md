# Source-key namespaces in the prompt study

Owner: [#3056](https://github.com/4444J99/limen/issues/3056). [Checked crosswalk](source-key-namespace-v1.json).

The study has three short-key namespaces. The values identify different things and must not be joined as if they were interchangeable.

| Key | Exact derivation and role |
|---|---|
| Snapshot column | First 12 SHA256 hex characters of the native header ID, newline, then full decoded-source SHA256. Used by the ordered storage-view graph and authoring review. |
| Legacy path key | First 12 SHA256 hex characters of the captured source path. Used in the `column` field of the unknown-retention review and reply-order findings. It is a captured locator fingerprint. |
| Header key | First 12 SHA256 hex characters of the native header ID alone. It may repeat across captured files and cannot establish a complete logical history. |

The crosswalk covers the 36 source views used by the two legacy-key reports and the authoring comparison. Every row is derived from the existing private capture metadata; snapshot keys are unique within this checked set. No raw ID, path or full private hash is republished. The original captured records and all existing source keys are preserved.

| Legacy path key | Snapshot column | Header key | Captured positions |
|---|---|---|---:|
| f8c982e459f9 | b4c52155921b | 9e3d4b88ecb1 | 6 |
| 7cfdad517062 | a15de0ec3c19 | c2a966ff3e84 | 4 |
| e519eac9c84e | e80d96b1ddc1 | b8aa7836141e | 7 |
| 442d2f4c57a1 | 6ee880f30841 | 878574b5701d | 6 |
| 99e97e66e273 | 15f3337d94d2 | 4b107b112bf1 | 5 |
| d7d0f419cbc7 | 9aea23a72306 | 840131dd56b2 | 5 |
| ab7a1376abe1 | 562e7bb79447 | 909df890d093 | 5 |
| f25213f688aa | a9e23391da04 | 7345b96d3763 | 4 |
| 051d63f18947 | e2faeb980521 | 5691371177aa | 5 |
| 22e9905c43b0 | 938fea674f63 | 0957996f40fd | 55 |
| 3dde40cedc8f | 6fe85dcf37a6 | 27b9d61a9799 | 21 |
| e044f87430cc | 596356e364b4 | b09e26fc9708 | 22 |
| 3fff96b675de | 72c49d764397 | 6148afa990ff | 47 |
| af18495c8d25 | 2411a04578b8 | c13fcbe462fe | 4 |
| 4adc78bce9e8 | 07f5eabf151f | f505d8520483 | 5 |
| af291bc589fc | 0dadb9e49cdb | 9ffa06e9969b | 9 |
| 8ea40621c7c3 | dd69a72b3186 | f1aca08fd9b5 | 9 |
| 0eea18215964 | f4ccfc0806e4 | 0e3a7485609d | 7 |
| fd5bc8b7b3d6 | fc146198d418 | 30ce6a3e8469 | 4 |
| 58ef6a507966 | e80ac5fd3f0b | d4998e959092 | 10 |
| f3152fff00ef | 701ccd52b6f2 | a37590015a82 | 38 |
| afef6db7962b | b006d9a8c817 | cdcb24ca41e3 | 8 |
| 2b653f5e4b39 | 9f5c72150a7a | 38b75c61a07d | 5 |
| 2ba5f1ccc49d | f75d65c06ca3 | cebc91c2abaf | 10 |
| e9f4c64c0ddd | 7bf905f8d2c0 | 83b330b493a3 | 28 |
| ea85c85f9575 | 655eac3fa9bb | 111ed8485d8c | 19 |
| 1ee193c93d44 | e4fbd18a160c | d09d21940481 | 3 |
| b34149af2f8f | dabafb660aa1 | 5fd4663fcaa7 | 2 |
| 435fbe538167 | 80c926a3f04e | c14318897f74 | 2 |
| 09bdae6ec388 | ea7b0ce6a138 | 8af81c96fb60 | 2 |
| 1d1991f08aaa | bb56707fb1ec | df6a0d97a316 | 2 |
| 35f23ad2bddd | 6da886379d27 | 25c3cd4a7ec1 | 2 |
| 95566e90ff56 | 0035e7b24072 | 6d76331c3254 | 3 |
| 26902db72375 | acd5feea6fc8 | 3be3ff2ba84f | 3 |
| db2b8f4c0c4e | 3f098759ab8f | 1d610d8b960a | 11 |
| 28c5955c6446 | 664bf0bd1627 | d182cb8c6d85 | 9 |

A moving source path can change a newly computed locator key. A snapshot key binds the captured content and header metadata, not current native-app acceptance. A shared header does not authorize adding an excluded parent tail or treating copied context as an independent intention. The earlier branch review's captured replies were also checked directly and all follow their inputs; it remains outside the confirmed backward-reply findings.
