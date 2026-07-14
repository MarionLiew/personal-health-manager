# DICOM import design

Planned implementation uses pydicom, SOPClassUID and actual dataset structure to identify RDSR.
Discovery supports individual files, extensionless files, directories, DICOMDIR and safe ZIP. It
must not log direct identity tags. Dose lookup priority is RDSR, dose screen, metadata, then an
explicitly labelled reference estimate. Images counts never estimate DLP.

Acquisition deduplication prioritizes IrradiationEventUID/AcquisitionUID and then study/series,
acquisition number, time and protocol. Reconstruction, window, MPR, VR and 3D series are not new
irradiations. This document describes the contract; implementation remains pending in phase 4.

