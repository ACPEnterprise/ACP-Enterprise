export interface AccessibleBranch {
  id: string;
  code: string;
  name: string;
  is_primary: boolean;
}

export interface AccessibleCompany {
  id: string;
  code: string;
  name: string;
  membership_id: string;
  default_branch_id: string | null;
  has_all_branch_access: boolean;
  branches: AccessibleBranch[];
}
