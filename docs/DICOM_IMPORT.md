# DICOM import design

The implementation uses pydicom, SOPClassUID and actual dataset structure to identify RDSR.
Discovery supports individual files, extensionless files, directories, DICOMDIR and safe ZIP. It
must not log direct identity tags. Dose lookup priority is RDSR, dose screen, metadata, then an
explicitly labelled reference estimate. Images counts never estimate DLP.

Acquisition deduplication prioritizes IrradiationEventUID/AcquisitionUID and then study/series,
acquisition number, time and protocol. Reconstruction, window, MPR, VR and 3D series are not new
irradiations. RDSR content trees are mapped to examination and irradiation-event fields; Total DLP
is stored separately from the event sum and is never added to it. Dose Screen detection exists, but
OCR candidate confirmation is not yet implemented.
