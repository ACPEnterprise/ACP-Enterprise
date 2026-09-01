import { apiClient } from "./client";
import type { Asset, AssetDetail } from "../types/assets";
const ROOT="/api/v1/assets";
export const listAssets=async(params?:Record<string,string>)=>(await apiClient.get<Asset[]>(ROOT,{params})).data;
export const getAsset=async(id:string)=>(await apiClient.get<AssetDetail>(`${ROOT}/${id}`)).data;
export const createAsset=async(data:Record<string,unknown>)=>(await apiClient.post<Asset>(ROOT,data)).data;
export const recordAssetEvidence=async(id:string,data:Record<string,unknown>)=>(await apiClient.post(`${ROOT}/${id}/evidence`,data)).data;
export const relateAsset=async(id:string,data:Record<string,unknown>)=>(await apiClient.post(`${ROOT}/${id}/relationships`,data)).data;
