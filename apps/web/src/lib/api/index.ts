/**
 * Unico ponto de entrada para dados. Componentes importam `api` daqui.
 *
 * - `health`, `auth` e `public` sao REAIS (mesma origem, /api/*): GET /api/health/ready, a autenticacao
 *   (docs/auth.md) e o portal publico de contribuicao (docs/public-flow.md).
 * - `statement` (resumo, extrato, pendencias e contribuicao em dinheiro do painel), `expenses` (docs/expenses.md) e
 *   `closings` (fechamento mensal e PDF) sao REAIS.
 *   Nada do site e simulado: nao ha mais camada de mocks.
 */
import { acceptInvitation, changePassword, getMe, login, logout, switchContext } from "./auth";
import { getReadiness } from "./health";
import { listClosings, createClosing, verifyClosing, reopenClosing, downloadClosingPdf } from "./closings";
import {
  approveExpense, cancelExpense, createExpense, downloadAttachment, getExpense, getOcrStatus, listCategories, listExpenses, payExpense,
  readReceipt, reimburseExpense, rejectExpense, requestCorrection, submitExpense, updateExpense, uploadAttachment,
} from "./expenses";
import {
  cancelStaffRequest, createStaffRequest, downloadRequestPhoto, getStaffRequest, listStaffRequests, resolveStaffRequest, startStaffRequest,
  uploadRequestPhoto,
} from "./staff-requests";
import { getPending, getStatement, getSummary, recordCashContribution } from "./statement";
import {
  activateCampaign, addCampaignItem, changeCampaignDelivery, clearCampaignImage, createCampaign, downloadCampaignImage, downloadCampaignReport,
  endCampaign, getCampaign, getCampaignDashboard, listCampaignOrders, listCampaigns, setCampaignImage, updateCampaign, updateCampaignItem,
} from "./campaigns";
import {
  createContribution, createOrder, getContribution, getPublicCampaign, getPublicCampaigns, getPublicSchool, getReceipt, renewCharge, sandboxPay,
} from "./public";

export const api: {
  health: { ready: typeof getReadiness };
  public: {
    school: typeof getPublicSchool;
    createContribution: typeof createContribution;
    contribution: typeof getContribution;
    renewCharge: typeof renewCharge;
    receipt: typeof getReceipt;
    sandboxPay: typeof sandboxPay;
    campaigns: typeof getPublicCampaigns;
    campaign: typeof getPublicCampaign;
    createOrder: typeof createOrder;
  };
  campaigns: {
    list: typeof listCampaigns;
    get: typeof getCampaign;
    create: typeof createCampaign;
    update: typeof updateCampaign;
    activate: typeof activateCampaign;
    end: typeof endCampaign;
    addItem: typeof addCampaignItem;
    updateItem: typeof updateCampaignItem;
    setImage: typeof setCampaignImage;
    clearImage: typeof clearCampaignImage;
    image: typeof downloadCampaignImage;
    dashboard: typeof getCampaignDashboard;
    orders: typeof listCampaignOrders;
    changeDelivery: typeof changeCampaignDelivery;
    report: typeof downloadCampaignReport;
  };
  expenses: {
    categories: typeof listCategories;
    list: typeof listExpenses;
    get: typeof getExpense;
    create: typeof createExpense;
    update: typeof updateExpense;
    upload: typeof uploadAttachment;
    download: typeof downloadAttachment;
    submit: typeof submitExpense;
    cancel: typeof cancelExpense;
    approve: typeof approveExpense;
    reject: typeof rejectExpense;
    requestCorrection: typeof requestCorrection;
    reimburse: typeof reimburseExpense;
    pay: typeof payExpense;
    ocrStatus: typeof getOcrStatus;
    readReceipt: typeof readReceipt;
  };
  requests: {
    list: typeof listStaffRequests;
    get: typeof getStaffRequest;
    create: typeof createStaffRequest;
    upload: typeof uploadRequestPhoto;
    download: typeof downloadRequestPhoto;
    start: typeof startStaffRequest;
    resolve: typeof resolveStaffRequest;
    cancel: typeof cancelStaffRequest;
  };
  closings: {
    list: typeof listClosings;
    create: typeof createClosing;
    verify: typeof verifyClosing;
    reopen: typeof reopenClosing;
    pdf: typeof downloadClosingPdf;
  };
  statement: {
    summary: typeof getSummary;
    entries: typeof getStatement;
    pending: typeof getPending;
    recordCash: typeof recordCashContribution;
  };
  auth: {
    login: typeof login;
    logout: typeof logout;
    me: typeof getMe;
    switchContext: typeof switchContext;
    changePassword: typeof changePassword;
    acceptInvitation: typeof acceptInvitation;
  };
} = {
  health: { ready: getReadiness },
  public: {
    school: getPublicSchool,
    createContribution,
    contribution: getContribution,
    renewCharge,
    receipt: getReceipt,
    sandboxPay,
    campaigns: getPublicCampaigns,
    campaign: getPublicCampaign,
    createOrder,
  },
  campaigns: {
    list: listCampaigns,
    get: getCampaign,
    create: createCampaign,
    update: updateCampaign,
    activate: activateCampaign,
    end: endCampaign,
    addItem: addCampaignItem,
    updateItem: updateCampaignItem,
    setImage: setCampaignImage,
    clearImage: clearCampaignImage,
    image: downloadCampaignImage,
    dashboard: getCampaignDashboard,
    orders: listCampaignOrders,
    changeDelivery: changeCampaignDelivery,
    report: downloadCampaignReport,
  },
  auth: { login, logout, me: getMe, switchContext, changePassword, acceptInvitation },
  expenses: {
    categories: listCategories,
    list: listExpenses,
    get: getExpense,
    create: createExpense,
    update: updateExpense,
    upload: uploadAttachment,
    download: downloadAttachment,
    submit: submitExpense,
    cancel: cancelExpense,
    approve: approveExpense,
    reject: rejectExpense,
    requestCorrection,
    reimburse: reimburseExpense,
    pay: payExpense,
    ocrStatus: getOcrStatus,
    readReceipt,
  },
  requests: {
    list: listStaffRequests,
    get: getStaffRequest,
    create: createStaffRequest,
    upload: uploadRequestPhoto,
    download: downloadRequestPhoto,
    start: startStaffRequest,
    resolve: resolveStaffRequest,
    cancel: cancelStaffRequest,
  },
  closings: {
    list: listClosings,
    create: createClosing,
    verify: verifyClosing,
    reopen: reopenClosing,
    pdf: downloadClosingPdf,
  },
  statement: {
    summary: getSummary,
    entries: getStatement,
    pending: getPending,
    recordCash: recordCashContribution,
  },
};

export * from "./types";
