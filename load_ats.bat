start /wait python main.py dt1=-180 overwrite=false partcode=mosenerg reportcode=fact_nczcfr,SR_PART_DEBT_BANKRUPT_REESTR
start /wait python main.py dt1=-5 overwrite=false reportcode=cfrliab,mtrx,PENYLIAB,cfrliabdpg,peny_uved,CFR_PART_BUH_INFO,cessinfo,komreestr,CFR_PART_DPMV_NOTICE,CFR_RD_CLOSE_NOTIF,necessity,assurance,CFR_CESS_DEBIT,CFR_PART_CESS_DEBT,CFR_CESS_PAYMENT,CFR_PART_FSK_REPORT_PAYMENT_STRUCT,CFR_PART_OVERALL_INVOICE_LAYOUT,CFR_PART_SF_OVERALL_INVOICE_LAYOUT,CFR_PART_CONSOLIDATED_INVOICE_XML_TMPL,CFR_PART_DOP_LIABREORG_ARMNT_NOTICE,UPGR_CONTRACT,CFR_PART_FORM_NOTICE,CFR_PART_RSBU_FORMDDS_F47,CFR_PART_DOP,CFR_PART_ACCEPT,CFR_PART_DOP_IND_K1K2_FAIL_NOTICE,CFR_PART_DOP_REP_FORMS47_STATUS,INVOICE_PERFORMANCE,CFR_NEWGP_PROP_DEPT,CFR_PART_KOMMOD_DELAY_TERM_SUPPLY_NOTICE,CFR_PART_KOMMOD_CHANGE_NOTICE,personal_message
start /wait python main.py dt1=-60 overwrite=false reportcode=matrix_peny_month,peny_uved_month,energy_comissioner_cfr,CFR_PART_RSV_BR_NCZ_KP_REP,CESSM,cesspeny,CFR_PART_DPMV_CHANGE_NOTICE,CFR_PART_DOP_REP_FACT_CALC_EE_PWR,sdd_monthly
start /wait python main.py dt1=-3 overwrite=false load_type=public partcode=mosenerg reportcode=trade_region_spub,carana_sell_units,curve_demand_offer,E_overflow_npz,losses_gtps,losses_regions,ppp_consumer_type,trade_zone,overflow_zsp,overflow_sechen_all_pub,big_nodes_prices_pub,trade_zsp,E_dispatch_units_npz
start /wait python main.py dt1=-60 overwrite=false load_type=public partcode=mosenerg reportcode=report_balance_BR,dispatch_report_zone,FRSRMN_NADB_DFO_ZONE,report_balance_rsv,MFORM_sale_volume_VR_zsp,dpmv_site_fine_object_list,DPMV_SITE_NEW_DOG_OBJECT_LIST,REESTR_NODES_ZSP,FRSTF_ATS_REPORT_PUBLIC_FSK,FRSV_REESTR_INFRAORG_USLUGI_XLS_ATS,FRSV_REESTR_INFRAORG_USLUGI_REGRF_ATS,mform_site_fact_pik_zsp,mform_site_fact_pik_F,SITE_KOM_CONS_SUM_VOLUME,dr_effect_month
start /wait python np_sr.py
python copy_reports.py