-- MySQL Script generated by MySQL Workbench
-- Tue May  3 13:12:43 2016
-- Model: New Model    Version: 1.0
-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='TRADITIONAL,ALLOW_INVALID_DATES';

-- -----------------------------------------------------
-- Schema encore
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `encore` DEFAULT CHARACTER SET utf8 ;
USE `encore` ;

-- -----------------------------------------------------
-- Table `users`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `users` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `email` VARCHAR(256) NOT NULL,
  `full_name` VARCHAR(150),
  `affiliation` VARCHAR(150),
  `creation_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `last_login_date` DATETIME,
  `can_analyze` bool DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `email_UNIQUE` (`email` ASC))
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `statuses`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `statuses` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(45) NOT NULL,
  PRIMARY KEY (`id`))
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `jobs`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `jobs` (
  `id` BINARY(16) NOT NULL,
  `user_id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `error_message` VARCHAR(512) NULL,
  `status_id` INT UNSIGNED NOT NULL,
  `geno_id` BINARY(16),
  `pheno_id` BINARY(16),
  `creation_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `modified_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `fk_jobs_users_idx` (`user_id` ASC),
  INDEX `fk_jobs_statuses1_idx` (`status_id` ASC),
  INDEX `fk_jobs_geno_idx` (`geno_id` ASC),
  INDEX `fk_jobs_pheno_idx` (`pheno_id` ASC),
  CONSTRAINT `fk_jobs_users`
    FOREIGN KEY (`user_id`)
    REFERENCES `users` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_jobs_statuses1`
    FOREIGN KEY (`status_id`)
    REFERENCES `statuses` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION),
  CONSTRAINT `fk_jobs_geno`
    FOREIGN KEY (`geno_id`)
    REFERENCES `genotypes` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION),
  CONSTRAINT `fk_jobs_pheno`
    FOREIGN KEY (`pheno_id`)
    REFERENCES `phenotyes` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `job_user_roles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `job_user_roles` (
  `id` INT UNSIGNED NOT NULL,
  `role_name` VARCHAR(45) NOT NULL,
  PRIMARY KEY (`id`),
  INDEX `fk_job_user_roles_idx` (`id` ASC)
);

-- -----------------------------------------------------
-- Table `job_users`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `job_users` (
  `job_id` BINARY(16) NOT NULL,
  `user_id` INT UNSIGNED NOT NULL,
  `role_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `created_by` INT UNSIGNED NOT NULL,
  `modified_by` INT UNSIGNED,
  `creation_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `modified_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`job_id`, `user_id`),
  INDEX `fk_job_users_user_idx` (`user_id` ASC),
  INDEX `fk_job_users_job_idx` (`job_id` ASC),
  CONSTRAINT `fk_job_users_user`
    FOREIGN KEY (`user_id`)
    REFERENCES `users` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_job_users_role`
    FOREIGN KEY (`role_id`)
    REFERENCES `job_user_roles` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION);

-- -----------------------------------------------------
-- Table `phenotypes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `phenotypes` (
  `id` BINARY(16) NOT NULL,
  `user_id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(512) NOT NULL,
  `orig_file_name` VARCHAR(512) NOT NULL,
  `md5sum` VARCHAR(32) NULL,
  `creation_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `fk_phenotypes_users_idx` (`user_id` ASC),
  CONSTRAINT `fk_phenotypes_users`
    FOREIGN KEY (`user_id`)
    REFERENCES `users` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION);

-- -----------------------------------------------------
-- Table `genotypes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `genotypes` (
  `id` BINARY(16) NOT NULL,
  `name` VARCHAR(512) NOT NULL,
  `creation_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`));

-- -----------------------------------------------------
-- function uuid_to_bin
-- -----------------------------------------------------

DELIMITER $$
CREATE DEFINER=`root`@`localhost` FUNCTION `uuid_to_bin`(s CHAR(36)) RETURNS binary(16)
    DETERMINISTIC
BEGIN
RETURN UNHEX(REPLACE(s,'-',''));
END$$

DELIMITER ;

-- -----------------------------------------------------
-- function bin_to_uuid
-- -----------------------------------------------------

DELIMITER $$
CREATE DEFINER=`root`@`localhost` FUNCTION `bin_to_uuid`(b BINARY(16)) RETURNS char(36) CHARSET utf8
    DETERMINISTIC
BEGIN
  DECLARE hex CHAR(32);
  SET hex = HEX(b);
  RETURN LOWER(CONCAT(LEFT(hex, 8), '-', MID(hex, 9,4), '-', MID(hex, 13,4), '-', MID(hex, 17,4), '-', RIGHT(hex, 12)));
END$$

DELIMITER ;

SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;

-- -----------------------------------------------------
-- Data for table `statuses` and `job_user_roles`
-- -----------------------------------------------------
START TRANSACTION;
INSERT INTO `statuses` (`id`, `name`) VALUES (DEFAULT, 'created');
INSERT INTO `statuses` (`id`, `name`) VALUES (DEFAULT, 'queued');
INSERT INTO `statuses` (`id`, `name`) VALUES (DEFAULT, 'started');
INSERT INTO `statuses` (`id`, `name`) VALUES (DEFAULT, 'cancel_requested');
INSERT INTO `statuses` (`id`, `name`) VALUES (DEFAULT, 'cancelled');
INSERT INTO `statuses` (`id`, `name`) VALUES (DEFAULT, 'failed');
INSERT INTO `statuses` (`id`, `name`) VALUES (DEFAULT, 'succeeded');
INSERT INTO `statuses` (`id`, `name`) VALUES (DEFAULT, 'quarantined');

INSERT INTO `job_user_roles` (`id`, `role_name`) VALUES (0, 'viewer');
INSERT INTO `job_user_roles` (`id`, `role_name`) VALUES (1, 'owner');

COMMIT;

