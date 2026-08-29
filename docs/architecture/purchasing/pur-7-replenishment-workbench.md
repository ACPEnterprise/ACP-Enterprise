# PUR.7 replenishment recommendation workbench

PUR.7 is a read-only, Company- and Branch-scoped Purchasing projection. An operator supplies an explicit target available quantity. The workbench combines authoritative Inventory quantity evidence with open, issued Purchase Order quantities and returns a deterministic recommendation, canonical digest, and source provenance.

Missing Inventory evidence fails closed. The projection does not select vendors, set purchasing policy, approve replenishment, create or change a Purchase Order, or write Inventory, AP, Accounting, Payments, Job material, or Economics facts. PUR.8 owns any later approval and PO linkage.

PUR.8 adds immutable approve/reject evidence. Approval replays the original inputs against current authoritative evidence and fails closed when the evidence digest changes. Approval requires an explicit Vendor, quantity, PO identity, currency, and unit cost, then atomically links exactly one draft PO through existing Purchasing tables.
