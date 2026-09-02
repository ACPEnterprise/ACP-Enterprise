import { useMutation,useQuery,useQueryClient } from "@tanstack/react-query";
import { createAsset,draftAssetPolicy,getAsset,getAssetOperationalReadiness,listAssetActions,listAssets,previewAssetImport,recordAssetAction,recordAssetEvidence,relateAsset } from "../api/assets";
const keys={all:["assets"] as const,list:(q:string)=>["assets","list",q] as const,detail:(id:string)=>["assets",id] as const,actions:(id:string)=>["assets",id,"actions"] as const};
export const useAssets=(q="")=>useQuery({queryKey:keys.list(q),queryFn:()=>listAssets(q?{q}:undefined)});
export const useAsset=(id:string)=>useQuery({queryKey:keys.detail(id),queryFn:()=>getAsset(id),enabled:Boolean(id)});
export const useAssetActions=(id:string)=>useQuery({queryKey:keys.actions(id),queryFn:()=>listAssetActions(id),enabled:Boolean(id)});
export const useAssetOperationalReadiness=()=>useQuery({queryKey:["assets","operational-readiness"],queryFn:getAssetOperationalReadiness});
export function useAssetMutations(){const client=useQueryClient(),refresh=()=>client.invalidateQueries({queryKey:keys.all});return {
 create:useMutation({mutationFn:createAsset,onSuccess:refresh}),
 evidence:useMutation({mutationFn:({id,data}:{id:string;data:Record<string,unknown>})=>recordAssetEvidence(id,data),onSuccess:refresh}),
 relate:useMutation({mutationFn:({id,data}:{id:string;data:Record<string,unknown>})=>relateAsset(id,data),onSuccess:refresh}),
 action:useMutation({mutationFn:({id,data}:{id:string;data:Record<string,unknown>})=>recordAssetAction(id,data),onSuccess:refresh}),
 policy:useMutation({mutationFn:draftAssetPolicy,onSuccess:refresh}),
 importPreview:useMutation({mutationFn:previewAssetImport,onSuccess:refresh}),
};}
