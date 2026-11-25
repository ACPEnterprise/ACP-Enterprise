# OM2 intelligent import mapping

Assignment `OM2-IMPORT-MAPPING-02` adds a deterministic CSV/XLSX header-mapping
preview using synthetic fixtures. Approved aliases map independently of column
position; unused fields remain explicitly preserved; competing columns for one
target become exceptions rather than guessed mappings. The canonical mapping
digest makes replay verifiable.

The preview never authorizes admission and performs no source or database
write. Protected files and actual All County imports were not used.
