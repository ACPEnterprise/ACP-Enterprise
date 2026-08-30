import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addCustomerContact,
  addCustomerNote,
  addCustomerProperty,
  archiveCustomer,
  checkCustomerDuplicates,
  createCustomer,
  getCustomer,
  listCustomers,
  listCustomerConsents,
  recordCustomerConsent,
  updateCustomer,
  updateCustomerContact,
  updateCustomerProperty,
} from "../api/customers";

export function useCustomerList(search: string, limit: number, offset: number, enabled = true) {
  return useQuery({
    queryKey: ["customers", search, limit, offset],
    queryFn: () => listCustomers(search, limit, offset),
    enabled,
  });
}
export function useCustomerDetail(customerId: string | null) {
  return useQuery({
    queryKey: ["customer", customerId],
    queryFn: () => getCustomer(customerId as string),
    enabled: Boolean(customerId),
  });
}
export function useCustomerConsents(customerId: string | null) {
  return useQuery({
    queryKey: ["customer-consents", customerId],
    queryFn: () => listCustomerConsents(customerId as string),
    enabled: Boolean(customerId),
  });
}

export function useCustomerMutations(customerId?: string) {
  const queryClient = useQueryClient();
  const refresh = async (id?: string) => {
    await queryClient.invalidateQueries({ queryKey: ["customers"] });
    if (id) {
      await queryClient.invalidateQueries({ queryKey: ["customer", id] });
    }
  };

  return {
    create: useMutation({
      mutationFn: createCustomer,
      onSuccess: (result) => refresh(result.customer.id),
    }),
    update: useMutation({
      mutationFn: (input: Parameters<typeof updateCustomer>[1]) =>
        updateCustomer(customerId as string, input),
      onSuccess: () => refresh(customerId),
    }),
    archive: useMutation({
      mutationFn: () => archiveCustomer(customerId as string),
      onSuccess: () => refresh(customerId),
    }),
    duplicateCheck: useMutation({ mutationFn: checkCustomerDuplicates }),
    addProperty: useMutation({
      mutationFn: (input: Parameters<typeof addCustomerProperty>[1]) =>
        addCustomerProperty(customerId as string, input),
      onSuccess: () => refresh(customerId),
    }),
    updateProperty: useMutation({
      mutationFn: ({
        propertyId,
        input,
      }: {
        propertyId: string;
        input: Parameters<typeof updateCustomerProperty>[2];
      }) => updateCustomerProperty(customerId as string, propertyId, input),
      onSuccess: () => refresh(customerId),
    }),
    addContact: useMutation({
      mutationFn: (input: Parameters<typeof addCustomerContact>[1]) =>
        addCustomerContact(customerId as string, input),
      onSuccess: () => refresh(customerId),
    }),
    updateContact: useMutation({
      mutationFn: ({
        contactId,
        input,
      }: {
        contactId: string;
        input: Parameters<typeof updateCustomerContact>[2];
      }) => updateCustomerContact(customerId as string, contactId, input),
      onSuccess: () => refresh(customerId),
    }),
    addNote: useMutation({
      mutationFn: (body: string) => addCustomerNote(customerId as string, body),
      onSuccess: () => refresh(customerId),
    }),
    recordConsent: useMutation({
      mutationFn: (input: Parameters<typeof recordCustomerConsent>[1]) =>
        recordCustomerConsent(customerId as string, input),
      onSuccess: async () => {
        await queryClient.invalidateQueries({
          queryKey: ["customer-consents", customerId],
        });
      },
    }),
  };
}
