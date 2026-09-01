import { useMutation,useQuery,useQueryClient } from "@tanstack/react-query";
import { createAsset,getAsset,listAssets,recordAssetEvidence,relateAsset } from "../api/assets";
const keys={all:["assets"] as const,list:(q:string)=>["assets","list",q] as const,detail:(id:string)=>["assets",id] as const};
export const useAssets=(q="")=>useQuery({queryKey:keys.list(q),queryFn:()=>listAssets(q?{q}:undefined)});
export const useAsset=(id:string)=>useQuery({queryKey:keys.detail(id),queryFn:()=>getAsset(id),enabled:Boolean(id)});
export function useAssetMutations(){const client=useQueryClient(),refresh=()=>client.invalidateQueries({queryKey:keys.all});return {
 create:useMutation({mutationFn:createAsset,onSuccess:refresh}),
 evidence:useMutation({mutationFn:({id,data}:{id:string;data:Record<string,unknown>})=>recordAssetEvidence(id,data),onSuccess:refresh}),
 relate:useMutation({mutationFn:({id,data}:{id:string;data:Record<string,unknown>})=>relateAsset(id,data),onSuccess:refresh}),
};}
