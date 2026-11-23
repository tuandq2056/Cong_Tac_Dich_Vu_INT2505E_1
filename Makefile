# Root Makefile for Cong_Tac_Dich_Vu_INT2505E_1
# Delegates WebChat targets to webchat/ directory.

.PHONY: verify test up down test-unit test-arch generate-tests test-api test-contract security security-secrets security-vuln security-dast

verify:
	$(MAKE) -C webchat verify

test:
	$(MAKE) -C webchat test

test-unit:
	$(MAKE) -C webchat test-unit

test-arch:
	$(MAKE) -C webchat test-arch

generate-tests:
	$(MAKE) -C webchat generate-tests

test-api:
	$(MAKE) -C webchat test-api

test-contract:
	$(MAKE) -C webchat test-contract

security:
	$(MAKE) -C webchat security

security-secrets:
	$(MAKE) -C webchat security-secrets

security-vuln:
	$(MAKE) -C webchat security-vuln

security-dast:
	$(MAKE) -C webchat security-dast

up:
	$(MAKE) -C webchat up

down:
	$(MAKE) -C webchat down
